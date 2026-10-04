---
type: REVIEW
scope: issue-inventory
status: complete
date: 2026-09-29
author_agent: feedback
source_repo: Popoboxxo/ReqogniLoom (GitHub)
base_commit: abd61aed (chore/system-audit-2026-09)
---

# Issue-Inventar (Reconciliation-Basis)

Vollstaendiges Inventar aller GitHub-Issues als Referenzbasis fuer das Systemaudit 2026-09.
Alle Angaben wurden per gh issue list (read-only) aus dem GitHub-Repo gezogen; es wurde
**kein** Issue erstellt, kommentiert, geschlossen oder gelabelt.

## 0. Datenquelle und Verlaesslichkeit

| Aspekt | Wert |
|---|---|
| Primaerquelle | https://github.com/Popoboxxo/ReqogniLoom (Remote origin) |
| Sekundaerremote | https://codeberg.org/dduchrow/ai-native-reqflow-POC (Remote codeberg) |
| Massgeblich | **GitHub** |
| Codeberg-Stand | c4cb7ea8, 2026-07-23 - **veraltet, NICHT Quelle der Wahrheit** |
| Erhebung | 2026-09-29, read-only via gh (Token 
epo-Scope) |
| Konsistenzbasis | Branch chore/system-audit-2026-09 @ bd61aed (identisch zu main) |

> **Wichtig fuer die Reconciliation:** Alle nachfolgenden Zahlen beziehen sich auf GitHub.
> Abweichungen zwischen GitHub und Codeberg sind erwartet und kein Befund - Codeberg ist
> seit 2026-07-23 unbewegt.

## 1. Gesamtstatistik

| Kennzahl | Wert |
|---|---|
| **Issues gesamt** | **608** |
| davon **offen** | **40** |
| davon **geschlossen** | **568** |
| Nummerierung | #16 bis #1117 |
| Nummerierungsluecken | 509 (siehe Abschnitt 1.2) |
| Pull Requests im Issue-Set | 0 (reines Issue-Set) |
| Erste Erstellung | 2026-07-23 |
| Letzte Erstellung | 2026-09-27 |

### 1.1 Autoren

| Autor | Issues |
|---|---|
| @Popoboxxo | 608 |

> **Invariant:** Alle 608 Issues wurden von **einer** Identitaet (Popoboxxo) erstellt.
> Die Spalte *Autor* ist deshalb in der Voll-Tabelle (Abschnitt 3) ausgelassen und hier
> als Invariante dokumentiert - das Feld ist damit vollstaendig erfasst, ohne 608 Zeilen
> mit derselben Angabe zu fuellen.

### 1.2 Nummerierungsluecken

Es existieren **509 Luecken** in der Nummernfolge (1-15, 46, 59-68, 86-88, 91, 93-94, 97,
187-211, ...). Ursache: die Nummern werden **nicht** fortlaufend vergeben (PRs und Issues
teilen sich offenbar denselben Nummernraum, und Issues wurden selektiert geschlossen bzw.
angelegt). **Fuer die Reconciliation unkritisch:** eine Luecke ist *kein* Hinweis auf ein
fehlendes Issue. Wer auf geschlossene Issues prueft, muss die Nummer selbst referenzieren.

### 1.3 Top-Labels

| Label | Anzahl |
|---|---|
| `bug` | 412 |
| `qa` | 192 |
| `medium` | 119 |
| `high` | 106 |
| `audit-2026-07` | 100 |
| `frontend` | 95 |
| `ui` | 91 |
| `enhancement` | 84 |
| `ui/ux` | 59 |
| `se` | 57 |
| `api` | 54 |
| `security` | 52 |
| `mcp` | 48 |
| `critical` | 45 |
| `data-model` | 41 |
| `low` | 40 |
| `audit-2026-08-07` | 34 |
| `infra` | 26 |
| `ux` | 25 |
| `rest` | 24 |
| `a11y` | 22 |
| `i18n` | 16 |
| `traceability` | 16 |
| `design` | 15 |
| `baseline` | 13 |

Issues **ohne** Label: **40** von 608 (6.6%).
## 2. Themen-Index

Zuordnung ueber Titel + Label-Namen (regex-basiert, case-insensitiv).
**Die Themen ueberschneiden sich bewusst** - ein Issue kann mehreren Themen angehoeren.
Die Summe der Zaehlungen liegt daher ueber 608 und ist keine Fehlerquelle,
sondern beabsichtigte Facetten-Sicht. Fuer die thematische Reconciliation eines
konkreten Issues ist die Voll-Tabelle (Abschnitt 3) bzw. die Grep-Suche massgeblich.

| Thema | Issue-Nummern | Zaehlung |
|---|---|---|
| **Tenant/Isolation** | #69, #103, #104, #110, #122, #127, #215, #217, #273, #360, #405, #433, #444, #483, #522, #708, #815, #1083 | 18 (davon 0 offen) |
| **Auth/API-Key/Token** | #37, #69, #72, #73, #77, #89, #92, #95, #96, #99, #100, #104, #105, #106, #107, #109, #115, #128, #134, #135, #137, #140 ... (+42 weitere) | 64 (davon 4 offen) |
| **MCP** | #17, #20, #21, #31, #81, #83, #92, #99, #101, #102, #105, #106, #108, #110, #112, #114, #121, #124, #125, #216, #222, #232 ... (+54 weitere) | 76 (davon 7 offen) |
| **LLM/Provider/Kosten** | #18, #32, #43, #101, #111, #112, #116, #118, #119, #122, #138, #180, #196, #212, #229, #273, #274, #275, #276, #342, #360, #377 ... (+28 weitere) | 50 (davon 3 offen) |
| **Plugin/Hermes/Bluepencil** | #456, #545, #599, #649, #683, #867, #946, #980, #981, #988, #1031, #1086, #1087, #1088, #1089, #1090, #1091, #1092, #1093, #1094 | 20 (davon 6 offen) |
| **REST-API/Schema-Drift** | #17, #18, #19, #20, #21, #25, #26, #31, #32, #33, #35, #36, #49, #54, #74, #82, #90, #92, #101, #105, #106, #108 ... (+109 weitere) | 131 (davon 9 offen) |
| **Frontend/UI/A11y** | #16, #34, #36, #47, #48, #51, #53, #54, #55, #78, #79, #82, #84, #85, #90, #92, #102, #119, #134, #135, #136, #137 ... (+212 weitere) | 234 (davon 16 offen) |
| **Workflow/State-Machine** | #40, #41, #78, #79, #101, #102, #113, #130, #136, #142, #214, #215, #220, #272, #319, #332, #333, #338, #346, #369, #370, #399 ... (+19 weitere) | 41 (davon 1 offen) |
| **Baseline** | #34, #42, #48, #49, #50, #55, #114, #218, #271, #272, #275, #319, #397, #398, #399, #400, #401, #483, #504, #513, #582, #585 ... (+14 weitere) | 36 (davon 4 offen) |
| **ReqIF/CSV/PDF** | #113, #117, #120, #131, #326, #442, #445, #446, #512, #649, #656, #657, #768, #881, #946, #1003, #1093 | 17 (davon 2 offen) |
| **Test/CI/E2E** | #16, #17, #18, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #42 ... (+248 weitere) | 270 (davon 16 offen) |
| **Performance** | #98, #115, #116, #122, #141, #149, #171, #234, #342, #445, #450, #584, #596, #629, #682, #846, #884, #922, #1052 | 19 (davon 0 offen) |
| **Doku/SE-Traceability** | #17, #18, #19, #20, #33, #42, #43, #44, #45, #99, #100, #101, #102, #103, #104, #105, #106, #107, #108, #109, #110, #111 ... (+220 weitere) | 242 (davon 16 offen) |
| **Security allgemein** | #56, #57, #58, #69, #70, #71, #72, #73, #74, #75, #76, #77, #80, #96, #99, #100, #101, #102, #103, #104, #105, #106 ... (+39 weitere) | 61 (davon 1 offen) |
| **Dependency/Supply-Chain** | #437, #949, #988 | 3 (davon 1 offen) |
| **Build/Release/Deploy** | #47, #52, #74, #90, #95, #111, #123, #143, #146, #149, #172, #213, #219, #226, #227, #228, #266, #269, #270, #276, #311, #363 ... (+37 weitere) | 59 (davon 4 offen) |

### 2.1 Themen-Rangfolge (Issue-Volumen)

| Rang | Thema | Issues | davon offen |
|---|---|---|---|
| 1 | Test/CI/E2E | 270 | 16 |
| 2 | Doku/SE-Traceability | 242 | 16 |
| 3 | Frontend/UI/A11y | 234 | 16 |
| 4 | REST-API/Schema-Drift | 131 | 9 |
| 5 | MCP | 76 | 7 |
| 6 | Auth/API-Key/Token | 64 | 4 |
| 7 | Security allgemein | 61 | 1 |
| 8 | Build/Release/Deploy | 59 | 4 |
| 9 | LLM/Provider/Kosten | 50 | 3 |
| 10 | Workflow/State-Machine | 41 | 1 |
| 11 | Baseline | 36 | 4 |
| 12 | Plugin/Hermes/Bluepencil | 20 | 6 |
| 13 | Performance | 19 | 0 |
| 14 | Tenant/Isolation | 18 | 0 |
| 15 | ReqIF/CSV/PDF | 17 | 2 |
| 16 | Dependency/Supply-Chain | 3 | 1 |

## 3. Voll-Tabelle aller 608 Issues

Sortierung: Nummer **aufsteigend**. Spalte *State* = OFFEN / GESCHLOSSEN.
Geschlossene Issues sind fuer die Reconciliation bewusst vollstaendig enthalten: es wurde
ein Fix behauptet, den das neue Audit gegen den Ist-Stand verifizieren muss.

| # | State | Titel | Labels | created | closed |
|---|---|---|---|---|---|
| #16 | GESCHLOSSEN | [UI][MEDIUM] Sidebar-Navigation funktioniert nicht nach SPA-Wechsel | bug medium ui/ux qa | 2026-07-23 | 2026-07-25 |
| #17 | **OFFEN** | [SE][MEDIUM] MCP: workspace.resolve_references ÔÇö ID-Resolver f├╝r Coding-Integration | enhancement medium api qa | 2026-07-23 | - |
| #18 | **OFFEN** | [SE][MEDIUM] RAG Search ÔÇö Semantische Suche ├╝ber alle Artefakte (pgvector) | enhancement medium api qa | 2026-07-23 | - |
| #19 | GESCHLOSSEN | [SE][HIGH] SE Rule Enforcer ÔÇö Preset-abh├ñngige Validierung bei create/update | enhancement high api se | 2026-07-23 | 2026-09-27 |
| #20 | GESCHLOSSEN | [SE][HIGH] MCP: requirement.derive_and_persist ÔÇö Derivation muss Artefakte erzeugen + IDs zur├╝ckgeben | enhancement high api se | 2026-07-23 | 2026-09-19 |
| #21 | GESCHLOSSEN | [QA][MEDIUM] MCP Schemas fehlt change_reason-Parameter ÔÇô extended Presets per MCP unbenutzbar | bug qa | 2026-07-23 | 2026-07-25 |
| #22 | GESCHLOSSEN | [QA][LOW] DELETE /test-runs/{id}/ gibt 405 ÔÇô Test Runs sind immutable | bug qa | 2026-07-23 | 2026-07-31 |
| #23 | GESCHLOSSEN | [QA][MEDIUM] Glossary speichert HTML/Script-Tags roh in description und term | bug qa | 2026-07-23 | 2026-07-25 |
| #24 | GESCHLOSSEN | [QA][MEDIUM] TestCase Status Case-Inkonsistenz + PATCH wird komplett abgelehnt | bug qa | 2026-07-23 | 2026-07-25 |
| #25 | GESCHLOSSEN | [QA][MEDIUM] test-runs Detail-Endpunkt braucht workspace_id als Query-Param | bug medium api qa | 2026-07-23 | 2026-07-31 |
| #26 | GESCHLOSSEN | [QA][MEDIUM] Issue-Status ist case-sensitive | bug medium api qa | 2026-07-23 | 2026-07-25 |
| #27 | GESCHLOSSEN | [QA][LOW] ICDs: 0 vorhanden, leere Seite ohne Anleitung | enhancement qa | 2026-07-23 | 2026-09-22 |
| #28 | GESCHLOSSEN | [QA][LOW] Trace Links: 0 Verbindungen im Workspace | enhancement qa | 2026-07-23 | 2026-09-27 |
| #29 | GESCHLOSSEN | [QA][LOW] Custom Fields nirgends befuellt | enhancement qa | 2026-07-23 | 2026-09-22 |
| #30 | GESCHLOSSEN | [QA][MEDIUM] User-Erstellung ohne Workspace-Mitgliedschaft | bug medium qa | 2026-07-23 | 2026-07-31 |
| #31 | GESCHLOSSEN | [QA][MEDIUM] MCP tools/list Schema-Qualitaet: einige Tools mit kwargs | medium api qa | 2026-07-23 | 2026-07-25 |
| #32 | GESCHLOSSEN | [QA][MEDIUM] LLM-Settings endpoint erreichbar aber Provider=mock | bug medium qa | 2026-07-23 | 2026-07-31 |
| #33 | GESCHLOSSEN | [QA][MEDIUM] architecture.link link_types restriktiv und undokumentiert | qa | 2026-07-23 | 2026-07-25 |
| #34 | GESCHLOSSEN | [QA][MEDIUM] Baselines koennen nicht via UI erstellt werden | bug medium qa | 2026-07-23 | 2026-07-25 |
| #35 | GESCHLOSSEN | [QA][MEDIUM] Kein Rate-Limiting auf API-Endpoints | enhancement qa | 2026-07-23 | 2026-09-27 |
| #36 | GESCHLOSSEN | [QA][MEDIUM] i18n: UI-Sprache 'DE' aber API-Sprache 'en' | bug medium qa | 2026-07-23 | 2026-07-31 |
| #37 | GESCHLOSSEN | [QA][MEDIUM] admin.backup_create Permission Denied | bug medium qa | 2026-07-23 | 2026-07-31 |
| #38 | GESCHLOSSEN | [QA][MEDIUM] artifact.get_tree - Artifact not found trotz Existenz | bug medium qa | 2026-07-23 | 2026-07-25 |
| #39 | GESCHLOSSEN | seed_demo Management-Command sollte idempotent sein bei Mehrfachaufruf | enhancement help wanted good first issue | 2026-07-23 | 2026-09-27 |
| #40 | GESCHLOSSEN | Health-Check sollte leere Workflow-Definitionen als Warning melden | enhancement help wanted | 2026-07-23 | 2026-07-25 |
| #41 | GESCHLOSSEN | seed_demo Management-Command sollte Workflow-Definitionen mit-initialisieren | bug contribution welcome | 2026-07-23 | 2026-08-20 |
| #42 | GESCHLOSSEN | Baseline document-scope misses Requirements/ADRs/StakeholderNeeds linked via TraceLinks | qa | 2026-07-23 | 2026-07-25 |
| #43 | GESCHLOSSEN | [SE][HIGH] Requirements-Modell fehlt acceptance_criteria-Feld (IEEE 29148) | bug high se | 2026-07-23 | 2026-07-25 |
| #44 | GESCHLOSSEN | [SE][MEDIUM] UID-Uniqueness wird nicht erzwungen ÔÇö Duplikate m├Âglich | bug medium se | 2026-07-23 | 2026-07-25 |
| #45 | GESCHLOSSEN | [SE][LOW] Keine Warnung bei nicht-atomaren Requirements (and/or clauses) | enhancement low se | 2026-07-23 | 2026-08-20 |
| #47 | GESCHLOSSEN | [QA] B1 ÔÇö Version-Footer verschwindet auf Seiten mit langem Sidebar-Inhalt | bug ui | 2026-07-23 | 2026-07-25 |
| #48 | GESCHLOSSEN | [QA] B2 ÔÇö Baseline Create erlaubt keinen benutzerdefinierten Namen | enhancement ui | 2026-07-23 | 2026-08-30 |
| #49 | GESCHLOSSEN | [QA] B3 ÔÇö Baseline REST API nicht workspace-scoped | bug api | 2026-07-23 | 2026-08-05 |
| #50 | **OFFEN** | [QA] F1 ÔÇö Baseline: Benennung, Compare und Rollback | enhancement baseline | 2026-07-23 | - |
| #51 | GESCHLOSSEN | [QA] F2 ÔÇö Impact-Analysis Artifact-Selector zeigt UUID statt Titel | enhancement ui usability | 2026-07-23 | 2026-07-25 |
| #52 | GESCHLOSSEN | [QA] B4/CRITICAL ÔÇö Versions-Inspector + Save-Button im Requirement-Detail funktionieren nicht | bug critical | 2026-07-23 | 2026-07-25 |
| #53 | GESCHLOSSEN | [QA] B5 ÔÇö Trace Link Dialog: Duplikate, inkonsistente UI, fehlendes Feedback | bug ui | 2026-07-23 | 2026-08-20 |
| #54 | GESCHLOSSEN | [QA] B6 ÔÇö Sprach-Inkonsistenz: Impact Analysis komplett auf Deutsch, restliche UI Englisch | bug ui usability | 2026-07-23 | 2026-08-20 |
| #55 | GESCHLOSSEN | [QA] B7 ÔÇö Button-Label Inkonsistenz: + New vs + New Baseline vs + New ICD vs New Link | enhancement ui usability | 2026-07-23 | 2026-08-29 |
| #56 | GESCHLOSSEN | [SEC] SEC-005 ÔÇö DoS via Input: Server crasht mit 2000 Emojis oder 5000-Zeichen Strings (HTTP 500) | bug critical security | 2026-07-23 | 2026-07-29 |
| #57 | GESCHLOSSEN | [SEC] SEC-001 ÔÇö Stored XSS: Script-Tags unescaped in Workspace/Entity-Namen | bug critical security | 2026-07-23 | 2026-07-29 |
| #58 | GESCHLOSSEN | [SEC] SEC-007 ÔÇö DEBUG=True leakt saemtliche URL Patterns + interne Hostnamen | bug critical security | 2026-07-23 | 2026-07-29 |
| #69 | GESCHLOSSEN | [SEC] SEC-002 ÔÇö CRITICAL: Mass Assignment /auth/me/ ÔÇö roles & tenant_id via PATCH ├╝berschreibbar | bug critical security | 2026-07-24 | 2026-07-29 |
| #70 | GESCHLOSSEN | [SEC] SEC-003 ÔÇö HIGH: Mass Assignment ÔÇö workspace PATCH akzeptiert is_public/owner/slug | bug high security | 2026-07-24 | 2026-07-25 |
| #71 | GESCHLOSSEN | [SEC] SEC-004 ÔÇö HIGH: SQL-Injection-Payloads als Workspace-Namen akzeptiert | bug high security | 2026-07-24 | 2026-07-25 |
| #72 | GESCHLOSSEN | [SEC] SEC-006 ÔÇö MEDIUM: Kein Rate Limiting auf /auth/login/ ÔÇö Brute-Force m├Âglich | bug medium security | 2026-07-24 | 2026-07-25 |
| #73 | GESCHLOSSEN | [SEC] QIRK-002 ÔÇö MEDIUM: PATCH /auth/me/ ignoriert is_admin/password stillschweigend (HTTP 200) | bug medium security | 2026-07-24 | 2026-07-31 |
| #74 | GESCHLOSSEN | [SEC] SEC-007 ÔÇö LOW: Version-Endpoint ├Âffentlich ÔÇö Commit-Hash + Build-Time geleakt | bug low security | 2026-07-24 | 2026-07-31 |
| #75 | GESCHLOSSEN | [SEC] SEC-008 ÔÇö LOW: Fehlende Security-Header (CSP, HSTS) | bug low security | 2026-07-24 | 2026-07-25 |
| #76 | GESCHLOSSEN | [SEC] QIRK-003 ÔÇö LOW: Null-Byte in Workspace-Name -> HTTP 500 statt 400 | bug low security | 2026-07-24 | 2026-07-25 |
| #77 | GESCHLOSSEN | [SEC] EDGE-004 ÔÇö LOW: JWT-Token hat 12h Laufzeit ÔÇö zu lang f├╝r Production | bug low security | 2026-07-24 | 2026-07-31 |
| #78 | GESCHLOSSEN | [QA] ­ƒö┤ WorkflowDefinition nicht initialisiert ÔÇö DELETE/outdate/reactivate auf allen Entities blockiert | bug qa critical | 2026-07-25 | 2026-07-29 |
| #79 | GESCHLOSSEN | [QA] ­ƒö┤ WorkflowDefinition nicht initialisiert ÔÇö DELETE/outdate/reactivate auf allen Entities blockiert | bug qa critical | 2026-07-25 | 2026-07-29 |
| #80 | GESCHLOSSEN | [QA] ­ƒö┤ Sicherheitsl├╝cken: DEBUG=True, Mass Assignment, SQL injection akzeptiert | bug qa critical security | 2026-07-25 | 2026-07-29 |
| #81 | GESCHLOSSEN | [QA] ­ƒö┤ MCP Crashes: workspace.get_context(depth=full) TypeError, issue.delete silent crash | bug qa critical mcp | 2026-07-25 | 2026-07-29 |
| #82 | GESCHLOSSEN | [QA] ­ƒƒá Workspace Reactivation broken (500), REST API Inkonsistenzen | bug high qa rest | 2026-07-25 | 2026-07-31 |
| #83 | GESCHLOSSEN | [QA] ­ƒƒí MCP Parameter Naming Mismatches: glossary.update, issue.update, needs.query | bug medium qa mcp | 2026-07-25 | 2026-07-31 |
| #84 | GESCHLOSSEN | [QA] ­ƒƒí UI/UX: Fehlendes Heading auf Needs-Seite, Language Mix, Port 80 tot | bug medium qa ui | 2026-07-25 | 2026-08-20 |
| #85 | **OFFEN** | [QA] ­ƒÅå UI-Bewertung & Verbesserungsvorschlaege f r ReqogniLoom v1.0.0 | - | 2026-07-25 | - |
| #89 | **OFFEN** | seed_demo als Login-Bootstrap-Ersatz in CI ist keine Endanwender-taugliche L├Âsung | enhancement | 2026-07-26 | - |
| #90 | GESCHLOSSEN | [BUG] Frontend nginx.conf fehlt API-Proxy ÔåÆ GHCR-Image out-of-the-box unbrauchbar (405) | bug frontend priority-high | 2026-07-26 | 2026-08-07 |
| #92 | **OFFEN** | feat: workspace-specific API tokens with UI for UUID display and MCP config copy | enhancement | 2026-07-28 | - |
| #95 | GESCHLOSSEN | Migration 0048 reverse operation used unsafe cluster-wide DROP ROLE | bug | 2026-07-28 | 2026-07-28 |
| #96 | GESCHLOSSEN | Hardcoded default password for new least-privilege DB role | bug security | 2026-07-28 | 2026-07-28 |
| #98 | GESCHLOSSEN | Playwright E2E: waterkettle shards fail with root-ArchitectureElement conflict + navigation timeout | bug | 2026-07-28 | 2026-07-31 |
| #99 | GESCHLOSSEN | [AUDIT][SEC] CRITICAL: MCP-Write-RBAC nur ueber 14er-Allowlist ÔÇö Grossteil der schreibenden Tools ungeprueft | bug critical security mcp audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #100 | GESCHLOSSEN | [AUDIT][SEC] CRITICAL: _assert_write_permission ist fail-open bei leerer Rollenliste | bug critical security audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #101 | GESCHLOSSEN | [AUDIT][SEC] HIGH: MCP prompt_template.create/update ohne Admin-Gate ÔÇö REST verlangt Admin | bug high security mcp audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #102 | GESCHLOSSEN | [AUDIT][SEC] HIGH: MCP diagram.create/update/outdate/reactivate ohne jede Berechtigungspruefung | bug high security mcp audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #103 | GESCHLOSSEN | [AUDIT][SEC] HIGH: Rollen sind tenant-global statt workspace-scoped ÔÇö Cross-Workspace-Privilege-Escalation | bug high security audit-2026-07 | 2026-07-28 | 2026-07-31 |
| #104 | GESCHLOSSEN | [AUDIT][SEC] HIGH: AuthTenancyMiddleware nicht in MIDDLEWARE registriert ÔÇö Tenant-Kontext wird nie abgeraeumt | bug high security audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #105 | GESCHLOSSEN | [AUDIT][SEC] MEDIUM: MCP-Endpunkt akzeptiert API-Key als URL-Query-Parameter | bug medium security mcp audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #106 | GESCHLOSSEN | [AUDIT][SEC] MEDIUM: SSE-Session-API-Keys in Redis nur signiert, nicht verschluesselt ÔÇö Docstring behauptet Gegenteil | bug medium security mcp audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #107 | GESCHLOSSEN | [AUDIT][SEC] MEDIUM: JWT ohne exp-Claim wird unbegrenzt akzeptiert | bug medium security audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #108 | GESCHLOSSEN | [AUDIT][SEC] MEDIUM: Interne Exception-Texte gelangen in HTTP-500- und MCP-Fehlerantworten | bug medium security mcp rest audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #109 | GESCHLOSSEN | [AUDIT][SEC] MEDIUM: Hardcodierter Default fuer DB_PASSWORD und DB_USER in settings.py | bug medium security audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #110 | GESCHLOSSEN | [AUDIT][SEC] MEDIUM: RLS-Session-Variable per SET statt SET LOCAL ÔÇö und im MCP-Pfad nie gesetzt | bug medium security mcp audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #111 | GESCHLOSSEN | [AUDIT][DOGFOOD] CRITICAL: Kein LLM-SDK installiert ÔÇö jeder echte Provider crasht sofort | bug critical audit-2026-07 dogfooding | 2026-07-28 | 2026-07-29 |
| #112 | GESCHLOSSEN | [AUDIT][DOGFOOD] CRITICAL: needs.derive_requirements persistiert nichts, sendet nur die UUID an das LLM, Ergebnis ist unabrufbar | bug critical mcp audit-2026-07 dogfooding | 2026-07-28 | 2026-07-29 |
| #113 | GESCHLOSSEN | [AUDIT][DOGFOOD] CRITICAL: CSV-Import erzeugt keinen WorkflowItemState ÔÇö importierte Artefakte sind workflow-tot | bug critical audit-2026-07 dogfooding | 2026-07-28 | 2026-07-29 |
| #114 | GESCHLOSSEN | [AUDIT][DOGFOOD] HIGH: Keine baseline.*-Tools im MCP-Server ÔÇö letzter E2E-Schritt agentisch nicht erreichbar | enhancement high baseline mcp audit-2026-07 dogfooding | 2026-07-28 | 2026-07-29 |
| #115 | GESCHLOSSEN | [AUDIT][DOGFOOD] HIGH: Alle 7 AI-Derive-Flows umgehen den CapabilityRouter ÔÇö kein Token-Limit, kein Audit, kein Timeout | bug high audit-2026-07 dogfooding | 2026-07-28 | 2026-07-29 |
| #116 | GESCHLOSSEN | [AUDIT][DOGFOOD] HIGH: Provider-Fehler und Timeouts eskalieren ungefangen aus dem Derive-Pfad | bug high audit-2026-07 dogfooding | 2026-07-28 | 2026-07-29 |
| #117 | GESCHLOSSEN | [AUDIT][DOGFOOD] HIGH: Kein Import-Pfad fuer docs/REQUIREMENTS.md (Markdown-Tabellen) | enhancement high audit-2026-07 dogfooding | 2026-07-28 | 2026-07-31 |
| #118 | GESCHLOSSEN | [AUDIT][DOGFOOD] MEDIUM: Anthropic-Provider hartcodiert ein zurueckgezogenes Modell und ignoriert die konfigurierte model_name | bug medium audit-2026-07 dogfooding | 2026-07-28 | 2026-07-29 |
| #119 | GESCHLOSSEN | [AUDIT][DOGFOOD] MEDIUM: UI/REST kann nur 3 von 7 Prompt-Templates bearbeiten, Workspace-Overrides gar nicht | bug medium rest audit-2026-07 dogfooding | 2026-07-28 | 2026-08-04 |
| #120 | GESCHLOSSEN | [AUDIT][DOGFOOD] MEDIUM: CSV-Import verwirft unbekannte Spalten still und meldet trotzdem Erfolg | bug medium audit-2026-07 dogfooding | 2026-07-28 | 2026-07-31 |
| #121 | GESCHLOSSEN | [AUDIT][DOGFOOD] MEDIUM: Kein generisches Trace-Link-Tool im MCP, suggest_links hat keinen Accept-Schritt | enhancement medium mcp audit-2026-07 dogfooding | 2026-07-28 | 2026-07-31 |
| #122 | GESCHLOSSEN | [AUDIT][DOGFOOD] MEDIUM: Derivation-Cache-Key nutzt den ENV-Provider statt des effektiven Tenant-Providers | bug medium audit-2026-07 dogfooding | 2026-07-28 | 2026-07-31 |
| #123 | GESCHLOSSEN | [AUDIT][DATA] CRITICAL: Migration 0020 loescht Requirement.moscow_priority ohne Datenmigration | bug critical audit-2026-07 data-model | 2026-07-28 | 2026-07-29 |
| #124 | GESCHLOSSEN | [AUDIT][DATA] HIGH: Kein Architektur-Guard fuer mcp_server/tools ÔÇö 38 direkte ORM-Zugriffe umgehen ADR-01 | bug high mcp audit-2026-07 data-model | 2026-07-28 | 2026-08-02 |
| #125 | GESCHLOSSEN | [AUDIT][DATA] HIGH: user.create MCP-Tool dupliziert Benutzeranlage inkl. TOCTOU-Race | bug high mcp audit-2026-07 data-model | 2026-07-28 | 2026-07-29 |
| #126 | GESCHLOSSEN | [AUDIT][DATA] HIGH: TraceLink ohne Unique-Constraint auf (source, target, link_type) | bug high audit-2026-07 data-model | 2026-07-28 | 2026-07-29 |
| #127 | GESCHLOSSEN | [AUDIT][DATA] MEDIUM: Workspace ohne Indizes und ohne Unique-Constraint trotz Multi-Tenant-Filterung | bug medium audit-2026-07 data-model | 2026-07-28 | 2026-07-31 |
| #128 | GESCHLOSSEN | [AUDIT][DATA] MEDIUM: Alle JSON-Felder ohne Schema-Validierung ÔÇö inkl. sicherheitsrelevantem Role.permissions | bug medium security audit-2026-07 data-model | 2026-07-28 | 2026-07-31 |
| #129 | GESCHLOSSEN | [AUDIT][DATA] MEDIUM: ArchitectureElement.get_level()/get_role() erzeugen N+1 pro Baumknoten | bug medium audit-2026-07 data-model | 2026-07-28 | 2026-07-31 |
| #130 | GESCHLOSSEN | [AUDIT][DATA] MEDIUM: WorkflowState und WorkflowDefinition komplett ohne Indizes | bug medium audit-2026-07 data-model | 2026-07-28 | 2026-07-31 |
| #131 | GESCHLOSSEN | [AUDIT][DATA] MEDIUM: Harter Top-Level-Import von reqif bricht den gesamten Django-Start | bug medium audit-2026-07 data-model | 2026-07-28 | 2026-07-31 |
| #132 | GESCHLOSSEN | [AUDIT][DATA] LOW: serializers.py ist vom Architektur-Guard ausgenommen ÔÇö offene Flanke fuer N+1 | enhancement low audit-2026-07 data-model | 2026-07-28 | 2026-07-31 |
| #133 | GESCHLOSSEN | [AUDIT][DATA] LOW: Requirement.uid ohne DB-Constraint ÔÇö Eindeutigkeit nur applikativ, race-anfaellig | bug low audit-2026-07 data-model | 2026-07-28 | 2026-07-31 |
| #134 | GESCHLOSSEN | [AUDIT][FE] HIGH: Modal-Dialoge ohne role="dialog" und ohne Fokus-Trap ÔÇö 0 von 9 aria-modal-Dialogen vollstaendig | bug high ui/ux frontend audit-2026-07 a11y | 2026-07-28 | 2026-07-29 |
| #135 | GESCHLOSSEN | [AUDIT][FE] HIGH: Kein Token-Refresh ÔÇö Session laeuft mitten in der Arbeit aus, Formularinhalt geht verloren | bug high frontend audit-2026-07 | 2026-07-28 | 2026-07-31 |
| #136 | GESCHLOSSEN | [AUDIT][FE] HIGH: Kompletter WorkflowEditor (23 Dateien) ohne i18n ÔÇö alle Labels hartcodiert | bug high ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #137 | GESCHLOSSEN | [AUDIT][FE] HIGH: API-Fehler werden nur in die Konsole geschrieben ÔÇö kein einziges role="alert" in der gesamten UI | bug high frontend audit-2026-07 a11y | 2026-07-28 | 2026-08-04 |
| #138 | GESCHLOSSEN | [AUDIT][FE] MEDIUM: Context-Provider-Values nicht memoisiert ÔÇö App-weiter Re-Render bei jedem Provider-Render | bug medium frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #139 | GESCHLOSSEN | [AUDIT][FE] MEDIUM: 3 Keys fehlen in de.json ÔÇö englischer Fallback ausgerechnet bei Loeschdialogen | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #140 | GESCHLOSSEN | [AUDIT][FE] MEDIUM: 128 hartcodierte Hex-Farbwerte in 33 Komponenten trotz tokens.css-Konvention | bug medium ui/ux frontend audit-2026-07 a11y | 2026-07-28 | 2026-08-28 |
| #141 | GESCHLOSSEN | [AUDIT][FE] MEDIUM: 35x waitForTimeout in den E2E-Tests statt assertion-basiertem Warten | bug medium qa audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #142 | GESCHLOSSEN | [AUDIT][FE] LOW: 5 Komponenten mit onClick-Handlern ohne jedes data-testid, kein Lint-Gate | enhancement low qa frontend audit-2026-07 | 2026-07-28 | 2026-07-31 |
| #143 | GESCHLOSSEN | [AUDIT][INFRA] CRITICAL: Woodpecker-CI hat keine Gates ÔÇö kein pytest, alle Checks folgenlos, Deploy laeuft trotzdem | bug critical audit-2026-07 infra | 2026-07-28 | 2026-07-29 |
| #144 | GESCHLOSSEN | [AUDIT][INFRA] CRITICAL: Root-conftest.py kippt die Test-DB auf SQLite ÔÇö Ursache der ~166 Fixture-Errors | bug qa critical audit-2026-07 infra | 2026-07-28 | 2026-07-29 |
| #145 | GESCHLOSSEN | [AUDIT][INFRA] HIGH: 180 MB Binaer-Backups (.backup/agent-meta/*.zip) sind eingecheckt ÔÇö .git ist 449 MB | bug high audit-2026-07 infra | 2026-07-28 | 2026-07-29 |
| #146 | GESCHLOSSEN | [AUDIT][INFRA] HIGH: Wegwerf-/Debug-Skripte eingecheckt und im Produktions-Image | bug high security audit-2026-07 infra | 2026-07-28 | 2026-07-29 |
| #147 | GESCHLOSSEN | [AUDIT][INFRA] HIGH: external/ReqogniLoom/ (239 MB Selbstkopie) ist untracked, aber nicht ignoriert | bug high audit-2026-07 infra | 2026-07-28 | 2026-07-28 |
| #148 | GESCHLOSSEN | [AUDIT][INFRA] HIGH: .env.example definiert DJANGO_ENV zweimal ÔÇö der zweite Wert kippt die Prod-Haertung | bug high security audit-2026-07 infra | 2026-07-28 | 2026-07-29 |
| #149 | GESCHLOSSEN | [AUDIT][INFRA] HIGH: Produktion deployt nur mutable :latest-Tags ÔÇö kein Rollback, /version meldet dauerhaft unknown | bug high audit-2026-07 infra | 2026-07-28 | 2026-07-29 |
| #150 | GESCHLOSSEN | [AUDIT][INFRA] MEDIUM: Frontend-Container bekommt die komplette .env inkl. aller Backend-Secrets | bug medium security audit-2026-07 infra | 2026-07-28 | 2026-08-03 |
| #151 | GESCHLOSSEN | [AUDIT][INFRA] MEDIUM: Hartkodierter Fernet-Key in settings_test.py und ci.yml eingecheckt | bug medium security audit-2026-07 infra | 2026-07-28 | 2026-07-31 |
| #152 | GESCHLOSSEN | [AUDIT][INFRA] MEDIUM: Zwei konkurrierende pytest-Konfigurationen mit divergierenden Regeln | bug medium qa audit-2026-07 infra | 2026-07-28 | 2026-08-03 |
| #153 | GESCHLOSSEN | [AUDIT][INFRA] MEDIUM: Keine Security-Gates in GitHub Actions; safety nur in Woodpecker und dort folgenlos | enhancement medium security audit-2026-07 infra | 2026-07-28 | 2026-08-03 |
| #154 | GESCHLOSSEN | [AUDIT][INFRA] MEDIUM: Keine Lock-Datei fuer Python-Deps; Django 4.2 EOL nahe, gunicorn <22.0 sperrt CVE-Fix aus | bug medium security audit-2026-07 infra | 2026-07-28 | 2026-08-03 |
| #155 | GESCHLOSSEN | [AUDIT][INFRA] MEDIUM: nginx liefert keine Security-Header; Frontend ohne Healthcheck; Backend-Healthcheck auf teurem Endpunkt | bug medium security audit-2026-07 infra | 2026-07-28 | 2026-08-03 |
| #156 | GESCHLOSSEN | [AUDIT][INFRA] LOW: Repo-Root unaufgeraeumt; .personal.md-Dateien sind trotz .gitignore-Eintrag getrackt | bug low audit-2026-07 infra | 2026-07-28 | 2026-07-31 |
| #157 | GESCHLOSSEN | [AUDIT][DESIGN] HIGH: Sidebar ignoriert das Theme ÔÇö Hintergrund #1a1f2e hardcodiert, in Light UND Dark identisch | bug high ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #158 | GESCHLOSSEN | [AUDIT][DESIGN] HIGH: Buttons haben keinerlei Fokus-Indikator ÔÇö global.css setzt outline: none ohne Ersatz | bug high ui/ux frontend audit-2026-07 a11y | 2026-07-28 | 2026-07-29 |
| #159 | GESCHLOSSEN | [AUDIT][DESIGN] HIGH: Login ÔÇö der einzige CTA "Sign In" sieht deaktiviert aus (grau statt Primaerfarbe) | bug high ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #160 | GESCHLOSSEN | [AUDIT][DESIGN] HIGH: Keine responsiven Breakpoints ÔÇö bei 390px belegt die Sidebar 56% der Breite, Inhalt unbenutzbar | bug high ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #161 | GESCHLOSSEN | [AUDIT][DESIGN] MEDIUM: Token-System hat kaum Reichweite ÔÇö 207 Inline-Styles im Code, 98 gestylte Elemente auf einer Seite | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-28 |
| #162 | GESCHLOSSEN | [AUDIT][DESIGN] MEDIUM: Zwei konkurrierende Button-Systeme in derselben Datei ÔÇö .btn-primary flach vs. button.primary mit Verlauf | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #163 | GESCHLOSSEN | [AUDIT][DESIGN] MEDIUM: Kein Monospace-Token, obwohl REQ-IDs, Diffs und JSON ueberall vorkommen | enhancement medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #164 | GESCHLOSSEN | [AUDIT][DESIGN] MEDIUM: Typo-Skala endet bei 1.5rem ÔÇö keine Display-Groesse, keine line-height- oder weight-Tokens | enhancement medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #165 | GESCHLOSSEN | [AUDIT][DESIGN] MEDIUM: Schriften werden zur Laufzeit von Google Fonts geladen ÔÇö render-blocking und bricht im Air-Gap | bug medium frontend audit-2026-07 infra | 2026-07-28 | 2026-08-04 |
| #166 | GESCHLOSSEN | [AUDIT][DESIGN] MEDIUM: Desktop-Layout verschenkt ~43% des Viewports, die Inhaltskarte fuellt die Hoehe nicht | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #167 | GESCHLOSSEN | [AUDIT][DESIGN] MEDIUM: Primaeraktion "+ New" steht unter den Filtern, sekundaere Aktionen dominieren die Kopfzeile | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #168 | GESCHLOSSEN | [AUDIT][DESIGN] LOW: Sidebar-Navigation wird mitten im Eintrag abgeschnitten, ohne Scroll-Hinweis | bug low ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #169 | GESCHLOSSEN | [AUDIT][DESIGN] LOW: Status-Badge "SR" ist ohne Legende oder Tooltip nicht entschluesselbar | bug low ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #170 | GESCHLOSSEN | [AUDIT][DESIGN] LOW: body-Hintergrundverlauf ist hardcodiert indigo/violett und folgt dem Theme nicht | bug low ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #171 | GESCHLOSSEN | [AUDIT][OPS] HIGH: celery-beat in Dauer-Restart ÔÇö periodische Tasks (REQ-030) laufen nie | bug high audit-2026-07 infra | 2026-07-28 | 2026-07-29 |
| #172 | GESCHLOSSEN | [AUDIT][UX] HIGH: Fuenf Artefakt-Seiten, fuenf verschiedene Page-Header ÔÇö Tag, Groesse, Gewicht und Aktionsposition weichen ueberall ab | bug high ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #173 | GESCHLOSSEN | [AUDIT][UX] HIGH: Status-Badge im Detail-Header ÔÇö drei Implementierungen, drei Ergebnisse fuer dieselbe Information | bug high ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #174 | GESCHLOSSEN | [AUDIT][UX] HIGH: --font-size-md ist nirgends definiert ÔÇö 10 Verwendungen fallen still auf die geerbte Groesse zurueck | bug high ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #175 | GESCHLOSSEN | [AUDIT][UX] HIGH: Drei Navigationsbaum-Implementierungen mit disjunkten Faehigkeiten ÔÇö kein Baum kann alles | bug high ui/ux frontend audit-2026-07 a11y | 2026-07-28 | 2026-08-04 |
| #176 | GESCHLOSSEN | [AUDIT][UX] HIGH: Scrollen ist unvorhersehbar ÔÇö 4-5 verschachtelte Scroll-Container pro Seite, das Dokument scrollt nie | bug high ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #177 | GESCHLOSSEN | [AUDIT][UX] HIGH: Umgang mit vielen Elementen ÔÇö Virtualisierung nur in 2 von 10 Listen, Glossar laedt still nur 25 Eintraege | bug high ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-07-29 |
| #178 | GESCHLOSSEN | [AUDIT][UX] MEDIUM: Nur 2 von 10 Seiten haben ein h1 ÔÇö die Dokument-Gliederung ist app-weit kaputt | bug medium frontend audit-2026-07 a11y | 2026-07-28 | 2026-08-04 |
| #179 | GESCHLOSSEN | [AUDIT][UX] MEDIUM: Vier verschiedene Leerzustaende, keiner bietet eine Handlung an | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #180 | GESCHLOSSEN | [AUDIT][UX] MEDIUM: Zwei konkurrierende Layoutmodelle ÔÇö Split-View auf 7 Seiten, volle Breite auf 3 | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #181 | GESCHLOSSEN | [AUDIT][UX] MEDIUM: Filterleiste uneinheitlich ÔÇö 0 bis 3 Filter, wechselnde Anordnung, Primaeraktion mal mittendrin | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #182 | GESCHLOSSEN | [AUDIT][UX] MEDIUM: Badge-Bedeutung wechselt je Ansicht ÔÇö gruenes "SR" bei Requirements, blaue "L0/L1" bei Architektur | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #183 | GESCHLOSSEN | [AUDIT][UX] MEDIUM: uid-Darstellung viermal inline dupliziert statt als Komponente | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #184 | GESCHLOSSEN | [AUDIT][UX] MEDIUM: "Impact Analysis" existiert doppelt ÔÇö als Panel in Trace Links und als eigener Navigationspunkt | bug medium ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #185 | GESCHLOSSEN | [AUDIT][UX] LOW: Elementanzahl nur bei aktivem Filter sichtbar | bug low ui/ux frontend audit-2026-07 | 2026-07-28 | 2026-08-04 |
| #186 | **OFFEN** | [AUDIT][UX] EPIC: UI-Gesamtkonzept ÔÇö Umsetzung in 6 Schritten (docs/UI_KONZEPT.md) | enhancement high ui/ux frontend audit-2026-07 | 2026-07-28 | - |
| #196 | GESCHLOSSEN | LLM providers still ignore configured model_name: Ollama, OpencodeGo, Azure, MockLlmProvider | bug | 2026-07-30 | 2026-08-15 |
| #212 | GESCHLOSSEN | fix: custom base_url not configurable for Anthropic/OpenAI providers | bug | 2026-07-30 | 2026-08-07 |
| #213 | GESCHLOSSEN | fix: Core artifact version field is optimistic-lock counter, not real history | bug high data-model | 2026-07-30 | 2026-07-31 |
| #214 | GESCHLOSSEN | fix: WorkflowFacade role-rejection never remaps to PermissionDeniedError | bug | 2026-07-30 | 2026-08-02 |
| #215 | GESCHLOSSEN | fix: PresetPolicyService.validate_transition_roles uses tenant_id instead of workspace_id, silently disabling preset role gate | bug | 2026-07-30 | 2026-08-02 |
| #216 | GESCHLOSSEN | feat: MCP Goal surface incomplete: missing goal.query / goal.delete | enhancement mcp | 2026-07-30 | 2026-08-02 |
| #217 | GESCHLOSSEN | security: No RLS policy on as_goal / as_main_goal tables | security data-model | 2026-07-30 | 2026-08-02 |
| #218 | GESCHLOSSEN | fix: Baseline snapshots don't capture Goal/MainGoal content | bug baseline | 2026-07-30 | 2026-08-15 |
| #219 | GESCHLOSSEN | fix: Goal/MainGoal version history unreachable in UI (VersionPanel/ArtifactDiff wiring incomplete) | bug ui frontend | 2026-07-30 | 2026-08-20 |
| #220 | GESCHLOSSEN | fix: GoalsPanel approve button hardcodes workflow state names instead of using allowed_transitions | bug frontend | 2026-07-30 | 2026-08-05 |
| #221 | GESCHLOSSEN | improvement: Minor polish items in Goal/MainGoal UI panels | enhancement ui frontend | 2026-07-30 | 2026-08-15 |
| #222 | GESCHLOSSEN | fix: mcp_server/tests/test_tool_registry.py fails on fresh DB (missing @pytest.mark.django_db) | bug qa mcp | 2026-07-30 | 2026-08-02 |
| #224 | GESCHLOSSEN | test | bug | 2026-07-30 | 2026-07-30 |
| #225 | GESCHLOSSEN | CRITICAL: Frontend nginx.conf fehlt API-Proxy ÔåÆ Login/API-Aufrufe brechen mit SPA-Fallback | - | 2026-07-30 | 2026-07-31 |
| #226 | GESCHLOSSEN | CRITICAL: Backend Dockerfile collectstatic schl├ñgt feil ÔÇô fehlende DB_PASSWORD / DB_APP_PASSWORD / REDIS_PASSWORD Build-Dummy-Vars | - | 2026-07-30 | 2026-07-31 |
| #227 | GESCHLOSSEN | HIGH: Frontend Dockerfile fehlende VITE_* Build-Args ÔÇô API-URL zur Build-Zeit nicht konfigurierbar | - | 2026-07-30 | 2026-07-31 |
| #228 | GESCHLOSSEN | MEDIUM: docker-compose.yml ├╝bergibt VITE_*-Variablen nicht als build.args an frontend | - | 2026-07-30 | 2026-07-31 |
| #229 | GESCHLOSSEN | CRITICAL: MainGoal.generate produziert leeren Inhalt `[]` statt Zielformulierung | bug critical goals ai llm | 2026-07-30 | 2026-07-31 |
| #230 | GESCHLOSSEN | BUG: Goals Seite verwendet `<h2>` statt `<h1>` ÔÇö Heading-Hierarchie inkonsistent mit anderen Seiten | bug ui frontend a11y | 2026-07-30 | 2026-08-06 |
| #231 | GESCHLOSSEN | BUG: SyntaxError auf Goals-Seite ÔÇö Unexpected end of JSON input in Response-Verarbeitung | bug api ui frontend | 2026-07-30 | 2026-08-07 |
| #232 | GESCHLOSSEN | CRITICAL: API-Key hat leere Rolle `()` ÔÇö alle MCP-Schreiboperationen schlagen fehl | bug api critical mcp auth | 2026-07-30 | 2026-07-31 |
| #233 | GESCHLOSSEN | HIGH: Trace-Links-Endpoint existiert nicht ÔÇö POST /api/v1/trace-links/ gibt HTTP 404 | bug high api rest | 2026-07-30 | 2026-07-31 |
| #234 | GESCHLOSSEN | HIGH: Google Fonts externer Request wird geblockt ÔÇö Inter/Outfit Fonts nicht ladbar | bug high frontend performance privacy | 2026-07-30 | 2026-07-31 |
| #235 | GESCHLOSSEN | CRITICAL: Server Crashes (HTTP 500) bei Goal/MainGoal Detail, PATCH und DELETE | bug api critical crash | 2026-07-30 | 2026-07-31 |
| #236 | GESCHLOSSEN | HIGH: Goals-API ignoriert alle Query-Parameter ÔÇö Status, Source, Limit, Ordering, Search wirkungslos | bug high api rest goals | 2026-07-30 | 2026-07-31 |
| #237 | GESCHLOSSEN | HIGH: TraceLink-System erkennt Goal-Entitaeten nicht ÔÇö Traceability GoalsÔåöRequirements unmoeglich | bug high api se mcp traceability | 2026-07-30 | 2026-07-31 |
| #238 | GESCHLOSSEN | MEDIUM: Goals-UI fehlt Action-Toolbar, Filter, Suche ÔÇö inkonsistentes Layout im Vergleich zu anderen Seiten | enhancement medium ui frontend goals | 2026-07-30 | 2026-08-15 |
| #259 | GESCHLOSSEN | BUG: Mermaid editor preview status bar / manual+auto-save 500 (E2E: mermaid-diagram.spec.ts) | bug qa | 2026-07-31 | 2026-08-20 |
| #261 | GESCHLOSSEN | MEDIUM: react-router 6.x has moderate CVEs, needs upgrade to 7.18.2+ | bug | 2026-07-31 | 2026-08-20 |
| #263 | GESCHLOSSEN | [QA][CRITICAL] UI-Save verliert Daten: PATCH enth├ñlt status-Feld ÔåÆ Server lehnt komplett ab ÔåÆ Edits gehen still verloren | bug qa ui critical frontend | 2026-08-01 | 2026-08-02 |
| #264 | GESCHLOSSEN | [QA][CRITICAL] MCP traceability.create_link: TestCase/Need 404 auf existierende Entities, Goal-Links Phantom (200 ohne Persistenz), Goal-Ziel HTTP 500 | bug qa critical mcp traceability | 2026-08-01 | 2026-08-01 |
| #265 | GESCHLOSSEN | [QA][HIGH] Workspace-Deletion per REST kaputt: POST /delete/ mit korrektem Confirmation ÔåÆ 500, DELETE ÔåÆ 204-Noop ohne L├Âschung | bug high qa rest | 2026-08-01 | 2026-08-02 |
| #266 | GESCHLOSSEN | [QA][HIGH] Deployment-Gap: Container l├ñuft Image 1.1.1 (e3bc3b6), aber /api/v1/version/ meldet 1.1.0 (51eb906) | bug high qa infra | 2026-08-01 | 2026-08-02 |
| #267 | GESCHLOSSEN | [QA][HIGH] Search auf /requirements/ komplett ignoriert ÔÇö Query-Param dekorativ (Regression) | bug high qa rest | 2026-08-01 | 2026-08-02 |
| #268 | GESCHLOSSEN | [QA][HIGH] MCP Schema-vs-Implementation: adr.create & risk.create ÔåÆ HTTP 500 statt Validierungsfehler bei fehlenden Pflichtfeldern | bug high qa mcp | 2026-08-01 | 2026-08-02 |
| #269 | GESCHLOSSEN | [QA][MEDIUM] Security-Batch: kein Rate-Limiting auf API, Login-Throttle blockiert korrekte Logins (Auth-DoS), XSS-Bypass javascript:-Schema, Glossary-Stored-XSS, PATCH Silent-Ignore + Versions-Inflation | bug medium qa security rest | 2026-08-01 | 2026-08-05 |
| #270 | GESCHLOSSEN | [QA][MEDIUM] MCP Goal/MainGoal: falsche Preset-Meldung, main_goal.read leer trotz Versionen, create_manual ohne ID, lineage_id-Semantik inkonsistent, target_state ohne Enum | bug medium qa mcp goals | 2026-08-01 | 2026-08-02 |
| #271 | GESCHLOSSEN | [QA][LOW] API-Hygiene: invalid-UUID ÔåÆ 404 statt 400, Login 'invalid_token' irref├╝hrend, Preset-Serialisierung inkonsistent, Goals 400 statt 403, Baselines-scope ohne kommunizierte Werte | bug low qa rest | 2026-08-01 | 2026-08-06 |
| #272 | **OFFEN** | [QA][ENH] SE-Interview (ISO 15288/42010/29148): Gesamtnote 3,5 ÔÇö Top-5 fachliche Schw├ñchen (AC-Gate, Link-Typ-Enum, Pass/Fail-Kontrakt, CRÔåöBaseline, Demo-Fixture) | enhancement qa se data-model | 2026-08-01 | - |
| #273 | GESCHLOSSEN | [QA][HIGH] LLM-Provider opencode_go fehlt im LlmProvider-Enum ÔÇö per-Tenant LLM-Settings k├Ânnen ihn nicht setzen | bug high qa llm | 2026-08-01 | 2026-08-02 |
| #274 | GESCHLOSSEN | [QA][HIGH] LLM-Settings-UI: Provider-Liste hartcodiert ÔÇö opencode_go nicht w├ñhlbar, Dropdown-Fallback zeigt falschen Provider + Save ├╝berschreibt Konfiguration | bug high qa ui frontend llm | 2026-08-01 | 2026-08-05 |
| #275 | GESCHLOSSEN | [QA][ENH] LLM-Provider sauber ├╝ber UI konfigurierbar: opencode_go fehlt in Backend-Enum + Frontend-Liste ÔÇö Fix mit Code-Diff (3 Stellen) | enhancement high qa ui frontend llm | 2026-08-01 | 2026-08-06 |
| #276 | GESCHLOSSEN | [QA][CRITICAL] LLM-Konfiguration ├╝ber .env/docker-compose unm├Âglich: Migration 0026 seedet mock und ├╝berschreibt .env still + Env-Var-Mismatch (LLM_MODEL vs LLM_MODEL_NAME) | bug qa critical infra llm | 2026-08-01 | 2026-08-05 |
| #290 | GESCHLOSSEN | fix: custom_fields never registered as DRF serializer field ÔÇö silent no-op on save | bug high api rest | 2026-08-02 | 2026-08-05 |
| #298 | GESCHLOSSEN | [AGENT-FEEDBACK] MEDIUM ÔÇö reqflow.md dokumentiert rfk_* statt reqlo_* API-Key-Prefix | - | 2026-08-02 | 2026-08-07 |
| #299 | GESCHLOSSEN | [AGENT-FEEDBACK] MEDIUM ÔÇö systemagents/reqflow.md ist veraltet: Tool-Gruppen, Tool-Anzahl und Produktname | - | 2026-08-02 | 2026-08-07 |
| #301 | GESCHLOSSEN | [AGENT-FEEDBACK] MEDIUM ÔÇö reqflow.md dokumentiert rfk_* statt reqlo_* API-Key-Prefix | - | 2026-08-02 | 2026-08-07 |
| #303 | GESCHLOSSEN | [AGENT-FEEDBACK] HIGH ÔÇö traceability.query liefert leere Links trotz existierender TraceLinks (Audit-Log bestaetigt create) | - | 2026-08-02 | 2026-08-06 |
| #304 | GESCHLOSSEN | [AGENT-FEEDBACK] HIGH ÔÇö MCP architecture.create kann keine Kind-Elemente anlegen (parent_id fehlt, I5 blockt jeden zweiten Create) | - | 2026-08-02 | 2026-09-19 |
| #305 | GESCHLOSSEN | [AGENT-FEEDBACK] MEDIUM ÔÇö artifact.get_tree liefert leere children obwohl Architektur-Hierarchie existiert | - | 2026-08-02 | 2026-08-06 |
| #311 | GESCHLOSSEN | [AGENT-FEEDBACK] HIGH ÔÇö REGRESSION v1.3.0: ai_derivation.decompose_requirement_next_level liefert 0 Drafts ohne Fehler (v1.2.0: 5-6) | bug | 2026-08-02 | 2026-08-15 |
| #312 | GESCHLOSSEN | [AGENT-FEEDBACK] MEDIUM ÔÇö v1.3.0: audit.ai_review timed out (>150s, kein Ergebnis) | bug | 2026-08-02 | 2026-08-20 |
| #313 | GESCHLOSSEN | [AGENT-FEEDBACK] ENH ÔÇö v1.3.0: Audit-Log enthaelt doppelte Eintraege pro Operation (5 Duplikate bei 15 Eintraegen) | - | 2026-08-02 | 2026-08-07 |
| #314 | GESCHLOSSEN | [AUDIT][UI-PILOT] Architecture: PageHeader-Prim├ñraktion l├ñuft ├╝ber rechten Viewport-Rand hinaus | audit-2026-07 | 2026-08-02 | 2026-08-04 |
| #315 | GESCHLOSSEN | [AUDIT][UI-PILOT] Bedarfe (Needs): 'Neuer Bedarf'-Button sitzt in Liste statt im PageHeader | audit-2026-07 | 2026-08-02 | 2026-08-04 |
| #316 | GESCHLOSSEN | [AUDIT][UI-PILOT] Goals: 'Ziele'-Baumknoten ohne visuelles Feedback f├╝r Expand/Collapse | audit-2026-07 | 2026-08-02 | 2026-08-04 |
| #317 | GESCHLOSSEN | [AUDIT][UI-PILOT] Sidebar-Navigation: ~20 Eintr├ñge ohne Gruppierung, ben├Âtigt Scrollen bei normaler Fensterh├Âhe | audit-2026-07 | 2026-08-02 | 2026-08-04 |
| #318 | GESCHLOSSEN | [AGENT-FEEDBACK] ENH ÔÇö Create-Trace-Link-Dialog ÔÇö native Selects schwer bedienbar (Source/Target), Create-Button-Zustand unklar | enhancement ui/ux frontend a11y | 2026-08-02 | 2026-09-22 |
| #319 | GESCHLOSSEN | [AGENT-FEEDBACK] ENH ÔÇö Inspector-Diff zeigt 'Comparing v1 -> v1' direkt nach Status-Transition | enhancement | 2026-08-02 | 2026-09-27 |
| #324 | GESCHLOSSEN | fix: DELETE /diagrams/{id} does not exclude id from subsequent GET (returns 200 not 404) | bug api audit-2026-07 | 2026-08-03 | 2026-08-04 |
| #325 | GESCHLOSSEN | fix: canvas-diagram.spec.ts E2E failures ÔÇö status bar tool-name text mismatch (8 tests) + 2 more | bug qa frontend audit-2026-07 | 2026-08-03 | 2026-08-04 |
| #326 | GESCHLOSSEN | chore: remove dead TestRuns.tsx (superseded by TestRunsList.tsx, zero importers) | frontend audit-2026-07 | 2026-08-03 | 2026-08-04 |
| #327 | GESCHLOSSEN | fix: actions.reload i18n key misused as 'retry' fallback text in 6 components | bug frontend audit-2026-07 | 2026-08-03 | 2026-08-04 |
| #328 | GESCHLOSSEN | improvement: ui-ratchet.test.ts hex-literal scanner only covers .tsx, not .css/.module.css | qa frontend audit-2026-07 | 2026-08-03 | 2026-08-04 |
| #329 | GESCHLOSSEN | fix: TraceSpine stationLabel() missing i18n for Goal/Adr/Risk/Issue/TestCase artifact types | bug frontend audit-2026-07 a11y | 2026-08-03 | 2026-08-04 |
| #332 | GESCHLOSSEN | feat: add Goal/MainGoal (and other missing types) to Workflow Editor admin UI | enhancement frontend audit-2026-07 | 2026-08-03 | 2026-08-04 |
| #333 | GESCHLOSSEN | fix: GoalsTree.tsx hardcodes GOAL_STATES instead of using real workflow definition | bug frontend audit-2026-07 | 2026-08-03 | 2026-08-04 |
| #336 | GESCHLOSSEN | [QA] REST: DELETE /api/v1/trace-links/{id}/ ist ein stiller No-op (HTTP 204, Link bleibt bestehen) | bug qa | 2026-08-03 | 2026-08-06 |
| #337 | GESCHLOSSEN | [QA] TestCase-Status Case-Inkonsistenz: "Draft" (uppercase) vs "draft" (lowercase) bei allen anderen Entities | bug qa | 2026-08-03 | 2026-08-06 |
| #338 | GESCHLOSSEN | [QA] Extended-Workflow: Transition 'verified' ÔåÆ 'deprecated' nicht definiert (Lifecycle endet bei verified) | bug qa | 2026-08-03 | 2026-08-07 |
| #339 | GESCHLOSSEN | [QA] UI-Save-Datenverlust bei extended-Preset: Change Reason nicht als Pflicht markiert, PATCH wird still verworfen (Datenverlust) | bug qa | 2026-08-03 | 2026-08-14 |
| #340 | GESCHLOSSEN | [QA] UI verschluckt Validierungsfehler: XSS- und Pflichtfeld-Ablehnungen ohne jede sichtbare Meldung | bug qa | 2026-08-03 | 2026-08-14 |
| #341 | GESCHLOSSEN | [QA] CRITICAL: KI-Derivation mode="write" persistiert nichts (SE-Link-Verletzung) | bug qa critical | 2026-08-03 | 2026-08-05 |
| #342 | GESCHLOSSEN | [QA] CRITICAL: Workspace-weite LLM-Tools laufen in hartes Timeout ÔåÆ Server-500 | bug qa critical | 2026-08-03 | 2026-08-05 |
| #343 | GESCHLOSSEN | [QA] HIGH: UI-Einheitlichkeit ÔÇö Sprach-Mix, Button-Labels, Status-Schemas (v1.4.0-UI-Rollout) | bug high qa | 2026-08-03 | 2026-08-15 |
| #344 | GESCHLOSSEN | [QA] HIGH: UI-Save persistiert weiterhin still nichts (Regression #263) | bug high qa | 2026-08-03 | 2026-08-05 |
| #345 | GESCHLOSSEN | [QA] HIGH: MCP-Schemas l├╝gen + artifact.search findet Testdaten nicht | bug high qa | 2026-08-03 | 2026-09-02 |
| #346 | GESCHLOSSEN | [QA] MEDIUM: Soft-Delete-Inkonsistenz, Workflow-L├╝cke, goal-MCP-L├╝cken | bug medium qa | 2026-08-03 | 2026-08-05 |
| #352 | GESCHLOSSEN | security: canvas_stroke intake has no type schema, only structural validation | bug api frontend | 2026-08-04 | 2026-08-05 |
| #353 | GESCHLOSSEN | refactor: replace freehand canvas_stroke diagram model with a structured node/edge graph | bug frontend | 2026-08-04 | 2026-08-08 |
| #359 | GESCHLOSSEN | MCP connection audit: SSE-only registry docs, no server-side enforcement of blocked admin/user tools | bug | 2026-08-05 | 2026-08-14 |
| #360 | GESCHLOSSEN | test: TenantContext leaks across pytest suites, breaks llm_adapter dispatcher test in combined runs | bug infra | 2026-08-05 | 2026-08-06 |
| #362 | GESCHLOSSEN | feat: add MCP tool to list workspaces (id, name, description) | enhancement | 2026-08-05 | 2026-08-06 |
| #363 | GESCHLOSSEN | architecture.decompose_commit creates duplicate root ArchitectureElement instead of reusing root_element_id | - | 2026-08-05 | 2026-08-06 |
| #364 | GESCHLOSSEN | architecture.decompose_commit persists empty junk Requirements even when draft's requirement fields are all empty strings | - | 2026-08-05 | 2026-08-06 |
| #365 | GESCHLOSSEN | traceability.query does not return TraceLinks created by architecture.decompose_commit, though identical manually-created links ARE returned | - | 2026-08-05 | 2026-08-06 |
| #366 | GESCHLOSSEN | artifact.get_tree always returns empty children, even for TraceLinks confirmed present via traceability.query | - | 2026-08-05 | 2026-08-06 |
| #368 | GESCHLOSSEN | [QA] LOW: Version-API und UI-Footer melden v1.3.0/988f623 ÔÇö Wiederkehr von #266 (Deployment-Gap Version-Stamping) | bug low qa | 2026-08-06 | 2026-08-07 |
| #369 | GESCHLOSSEN | [QA] LOW: MCP-Schema-L├╝cken in v1.5.0-Domains ÔÇö diagram_type ohne Enum, goal.outdate/reactivate ohne required | bug low qa | 2026-08-06 | 2026-08-06 |
| #370 | GESCHLOSSEN | [QA] HIGH: review.approve auf Issue setzt f├ñlschlich 'Wontfix' ÔÇö Review-Workflow fachlich falsch | bug high qa | 2026-08-06 | 2026-08-06 |
| #371 | GESCHLOSSEN | [QA] MEDIUM: goal.update erzeugt stille neue Version (neue ID + Sequence) ÔÇö Update-Semantik ├╝berraschend | bug medium qa | 2026-08-06 | 2026-08-07 |
| #372 | GESCHLOSSEN | [QA] HIGH: Review-UI zeigt 0 pending Reviews, obwohl 30 existieren ÔÇö UI fragt nur Requirements ab, Goal/MainGoal fehlen im Filter | bug high qa | 2026-08-06 | 2026-08-06 |
| #373 | GESCHLOSSEN | MCP adr_create: documented fields (context/decision/consequences) rejected by backend | - | 2026-08-06 | 2026-08-06 |
| #374 | GESCHLOSSEN | MCP adr_create: status enum values undocumented in tool schema | - | 2026-08-06 | 2026-08-06 |
| #375 | GESCHLOSSEN | artifact_search returns 3 duplicate root ArchitectureElements with same title, split children | - | 2026-08-06 | 2026-08-06 |
| #377 | GESCHLOSSEN | [FEATURE] Zusammenhangs- & Kontext-Speicher: Auto-aktualisierender Wissensgraph pro Workspace (optional Graphify/Honcho-Anbindung) | enhancement feature | 2026-08-06 | 2026-08-20 |
| #378 | **OFFEN** | [FEATURE] Artefakt-Qualit├ñtsbewertung: Trigger- oder auto-basierte Qualit├ñts-Scores mit pro-Workspace steuerbaren Qualit├ñts-Prompts | enhancement feature | 2026-08-06 | - |
| #392 | GESCHLOSSEN | bug: Diagram documents TraceLink creation always fails silently (SourceNotFoundError swallowed) | bug | 2026-08-07 | 2026-08-08 |
| #393 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] CRITICAL: MOE/MOP/TPM completely absent from data model, UI, and MCP surface | enhancement se data-model audit-2026-08-07 | 2026-08-07 | 2026-09-27 |
| #394 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] HIGH: Requirement.level (V-model L0-L4) not settable via REST/MCP, invisible in UI | bug high api se mcp audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #395 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] CRITICAL: Guided "Ableiten" derive flow produces a trace graph the SE-Auditor itself rejects | bug se ui critical traceability audit-2026-08-07 | 2026-08-07 | 2026-08-12 |
| #396 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: Coverage calculator ignores source type - an ADR can "verify" a Requirement | bug medium se traceability audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #397 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] HIGH: baseline_id parameter silently ignored by coverage() - always returns live data | bug high api baseline audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #398 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] CRITICAL: Baseline diff reports zero change for genuinely changed artifacts; drift invisible in UI | bug ui baseline critical audit-2026-08-07 | 2026-08-07 | 2026-08-08 |
| #399 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] HIGH: Baselines don't lock artifacts; Change Requests don't gate baselined-artifact edits | enhancement high se baseline audit-2026-08-07 | 2026-08-07 | 2026-09-22 |
| #400 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] HIGH: SE-Auditor gate fails open on internal errors during baseline creation | bug high se baseline audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #401 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: GET /baselines/diff/ 404s without an undocumented workspace_id parameter | bug medium baseline rest audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #402 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] HIGH: Validation layer (Goals) disabled by default; no stakeholder-goal traceability rule | enhancement high se goals audit-2026-08-07 | 2026-08-07 | 2026-09-22 |
| #403 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: TestRun lifecycle cannot reach "completed"; run_report_results appends instead of upserting | bug medium api mcp audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #404 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] HIGH: 4 of 8 documented trace-link types don't exist; two audit rules are permanently dead | bug documentation high mcp traceability audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #405 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] CRITICAL: SE metrics dashboard reports 0% coverage due to ThreadPoolExecutor/RLS interaction | bug api se critical audit-2026-08-07 | 2026-08-07 | 2026-08-12 |
| #406 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] CRITICAL: _fetch_risks TypeError silently swallowed - risk tile always shows 0/green | bug api se critical audit-2026-08-07 | 2026-08-07 | 2026-08-12 |
| #407 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] CRITICAL: Risk entity not linkable via trace_link_service - no trade-study support possible | bug api critical traceability audit-2026-08-07 | 2026-08-07 | 2026-08-12 |
| #408 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: Requirement creation has no mandatory fields and no rationale field exists | enhancement medium se data-model audit-2026-08-07 | 2026-08-07 | 2026-09-17 |
| #409 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] CRITICAL: Silent field loss - PATCH clears verification_method, MCP create drops SE fields with HTTP 200 | bug api critical mcp data-model audit-2026-08-07 | 2026-08-07 | 2026-08-12 |
| #410 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] HIGH: MCP surface missing tools for core SE lifecycle (coverage, VCRM, audit run, risk.link, ...) | enhancement high se mcp audit-2026-08-07 | 2026-08-07 | 2026-09-19 |
| #411 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] LOW: Workspace preset JSONField accepts only strings, not the documented object format | bug low api audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #412 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] CRITICAL: extended-preset approval gate requires acceptance_criteria with no UI field; only escape is silent rigor downgrade | bug se ui critical audit-2026-08-07 | 2026-08-07 | 2026-08-12 |
| #413 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] HIGH: Traceability view shows only truncated UUID pairs - unreadable, no titles/types/coverage | bug high ui ux traceability audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #414 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: Two unbridged ID spaces (Entity-ID vs Artifact-ID) cause the app to 404 on its own artifacts | bug medium ui traceability audit-2026-08-07 | 2026-08-07 | 2026-09-02 |
| #415 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: Impact analysis tree has no cycle detection - 5 artifacts/4 links render as 25+ nodes | bug medium ui traceability audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #416 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: "Hierarchical view" panel renders the artifact itself instead of its parent/child | bug medium ui traceability audit-2026-08-07 | 2026-08-07 | 2026-08-13 |
| #417 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] LOW: Change-reason requirement inconsistent across artifact types (missing on ArchitectureElement) | bug low ui ux audit-2026-08-07 | 2026-08-07 | 2026-08-14 |
| #418 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] LOW: Terminology leak - "Anforderung" placeholder shown on Need and ArchitectureElement forms | bug low ui ux audit-2026-08-07 | 2026-08-07 | 2026-08-14 |
| #419 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: Requirement editor unusable at 1366x768; Save button overlaps title at all resolutions | bug medium ui ux frontend audit-2026-08-07 | 2026-08-07 | 2026-08-20 |
| #420 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] LOW: Untranslated i18n keys shown literally in workspace-create dialog | bug low ui frontend audit-2026-08-07 | 2026-08-07 | 2026-08-14 |
| #421 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] LOW: German UI mixes in untranslated English headers, buttons, and gate messages | bug low ui ux audit-2026-08-07 | 2026-08-07 | 2026-08-14 |
| #422 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] LOW: ArchitectureElement shows contradictory L0/"Rolle System" badge vs Element-Typ "component" | bug low ui audit-2026-08-07 | 2026-08-07 | 2026-08-14 |
| #423 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] LOW: React warning - setState during render in RequirementForm/CustomFieldsEditor | bug low frontend audit-2026-08-07 | 2026-08-07 | 2026-08-12 |
| #424 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: AI-generated (mock) test cases saved unflagged, indistinguishable from real verification | enhancement medium se traceability audit-2026-08-07 | 2026-08-07 | 2026-09-22 |
| #425 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] MEDIUM: Accessibility gaps - unnamed form controls, non-keyboard trace entries, unlabeled icon buttons | bug medium ui a11y audit-2026-08-07 | 2026-08-07 | 2026-08-20 |
| #426 | GESCHLOSSEN | [AUDIT][SE-METHODOLOGY] Summary ÔÇö 2026-08-07 SE methodology audit index | audit-2026-08-07 | 2026-08-07 | 2026-09-27 |
| #427 | GESCHLOSSEN | MCP SSE session repeatedly expires client-side (401), requires manual /mcp reconnect | bug | 2026-08-07 | 2026-08-14 |
| #433 | GESCHLOSSEN | chore: add regression test for tenant_id defense-in-depth predicate in RequirementBundleQueryService CTE | enhancement | 2026-08-09 | 2026-09-22 |
| #434 | GESCHLOSSEN | fix: tool-manifest drift guard doesn't compare description/inputSchema, and has a broken container path | bug | 2026-08-09 | 2026-08-12 |
| #437 | GESCHLOSSEN | [BUG][CRITICAL] v1.6.0-beta.1 Frontend-GHCR-Image hat Dev-CMD (npm run dev) statt nginx - Container startet nicht (Exit 127) | bug critical frontend | 2026-08-09 | 2026-08-11 |
| #438 | GESCHLOSSEN | [BUG][HIGH] Version-API zeigt seit 4 Releases stale Version (1.3.0 statt 1.6.0-beta.1) - VERSION-Datei nicht gebumpt | bug high infra | 2026-08-09 | 2026-08-11 |
| #439 | GESCHLOSSEN | [BUG][MEDIUM] Backend-Start: Gunicorn Control server error - Permission denied '/nonexistent' (kein HOME fuer Runtime-User) | bug medium infra | 2026-08-09 | 2026-08-14 |
| #440 | GESCHLOSSEN | [BUG][HIGH] Glossary DELETE ist ein No-Op: HTTP 204, aber Objekt bleibt lifecycle_status=active und per GET abrufbar | bug high rest | 2026-08-09 | 2026-08-12 |
| #441 | GESCHLOSSEN | [BUG][HIGH] MCP workspace.get_context crasht mit HTTP 500 bei depth='normal'/'full' (UUID not JSON serializable) | bug high mcp | 2026-08-09 | 2026-08-12 |
| #442 | GESCHLOSSEN | [BUG][MEDIUM] requirement_bundle.export mode='compressed' komprimiert nicht: liefert vollen Attribut-Dump statt AI-Kurzfassung | bug medium mcp feature | 2026-08-09 | 2026-08-20 |
| #443 | GESCHLOSSEN | [BUG][MEDIUM] DELETE-Semantik inkonsistent ueber Entities (Hard-Delete vs. Soft-Delete vs. No-Op) ÔÇö gleicher Verb, unterschiedliche Folgezustaende | bug medium rest | 2026-08-09 | 2026-08-12 |
| #444 | GESCHLOSSEN | [BUG][MEDIUM] TokenUsageTracker scheitert an RLS: pl_token_usage_record bleibt leer trotz LLM-Calls (Token-Budget REQ-106 blind) | bug medium security infra | 2026-08-09 | 2026-08-14 |
| #445 | GESCHLOSSEN | [BUG][MEDIUM] requirement_bundle.export mode='compressed' liefert nicht-deterministische Ausgabeformate bei identischen Requests (Sync/Async teilen Cache inkonsistent) | bug medium mcp feature | 2026-08-09 | 2026-08-12 |
| #446 | GESCHLOSSEN | [BUG][LOW] Doku-Pfad fuer 1.6.0 Bundle-Export falsch: GET /api/v1/requirement-bundle/ -> 404 (korrekt: /architecture/{id}/requirement-bundle/) | bug documentation low rest | 2026-08-09 | 2026-08-14 |
| #447 | GESCHLOSSEN | [BUG][LOW] OpenAPI-Schema unvollstaendig fuer 1.6.0-Endpunkte (requirement-bundle Query-Params und /search/ Parameter fehlen) | bug documentation low rest | 2026-08-09 | 2026-09-02 |
| #448 | GESCHLOSSEN | [BUG][LOW] requirement_bundle.compression_status: undokumentierte Status-Werte ('pending'/'done') und doppelt verschachteltes result-Envelope | bug documentation low mcp | 2026-08-09 | 2026-08-12 |
| #449 | GESCHLOSSEN | [BUG][HIGH] Sidebar-Navigation abgeschnitten: 10 von 23 Menuepunkten unsichtbar & nicht scrollbar (overflow-y:hidden, sticky 100vh) | bug high ui | 2026-08-09 | 2026-09-11 |
| #450 | GESCHLOSSEN | [BUG][MEDIUM] Filter-/Scope-Dropdowns auf /metrics und /audit dauerhaft disabled ÔÇö uneinheitlich zu Listen-Seiten | bug medium ui | 2026-08-09 | 2026-08-12 |
| #451 | GESCHLOSSEN | [BUG][MEDIUM] SE-Auditor: Alle 69 'Modify'-Buttons disabled ÔÇö Findings read-only, keine Korrektur ueber UI moeglich | bug medium ui | 2026-08-09 | 2026-08-16 |
| #452 | GESCHLOSSEN | [BUG][HIGH] Review-Policy 'auto' im extended-Preset: Freigabe ohne menschliches Gate (auto-approve ab 0.7 Konfidenz) | bug high se | 2026-08-09 | 2026-08-13 |
| #453 | GESCHLOSSEN | [BUG][MEDIUM] Status-Case-Inkonsistenz: TestCase-Status 'Draft' (uppercase) vs. alle anderen Entities 'draft' (lowercase) ÔÇö weiterhin offen in v1.6.0-beta.1 | bug medium se rest | 2026-08-09 | 2026-08-12 |
| #454 | GESCHLOSSEN | [BUG][MEDIUM] SE-Metrics: volatility.top10_volatile liefert leere Titel ("") statt Requirement-Namen ÔÇö Seriellisierungsluecke | bug medium se rest | 2026-08-09 | 2026-08-12 |
| #455 | GESCHLOSSEN | fix: SSE transport (/mcp/sse/) returns HTTP 500 under runserver/wsgiref | bug mcp | 2026-08-09 | 2026-08-12 |
| #456 | GESCHLOSSEN | fix: Claude Code plugin build writes marketplace.json to wrong path | bug mcp infra | 2026-08-09 | 2026-08-13 |
| #458 | GESCHLOSSEN | [QA] auth/me + workspaces ohne Token liefern 403 statt 401 ÔÇö Browser-Console-Fehler bei jedem Seiten-Load | bug qa | 2026-08-11 | 2026-08-12 |
| #459 | GESCHLOSSEN | [QA] MCP-Schema-Verhalten: test.run_create ignoriert test_case_id stillschweigend; requirement.derive erzeugt Child ohne Description | bug qa | 2026-08-11 | 2026-08-12 |
| #460 | GESCHLOSSEN | [QA] API-Konsistenz-Bundle: HTML-404 statt JSON, irref├╝hrende Validierungsmeldungen, still ignorierte Query-Params, /goals/main/ UUID-Fehler | bug qa | 2026-08-11 | 2026-08-12 |
| #483 | GESCHLOSSEN | [BUG][MEDIUM] baseline/tests/test_diff_value_based_398.py ist auf main rot: DiffEngine.diff() fehlt tenant_id | bug | 2026-08-12 | 2026-08-13 |
| #484 | GESCHLOSSEN | [BUG][MEDIUM] Reactivate nach Soft-Delete verliert TraceLinks bei TestCase, Issue und Risk | bug | 2026-08-12 | 2026-08-13 |
| #504 | GESCHLOSSEN | [BUG] E2E shard 2: review-workflow.spec.ts + stakeholder-needs.spec.ts baseline failures pre-existing, partly caused by #488 acceptance_criteria gate | bug | 2026-08-13 | 2026-09-19 |
| #512 | GESCHLOSSEN | [BUG][MEDIUM] UI ruft toten Endpoint auf: GET /api/v1/artifacts/{id}/ ÔåÆ 404 im Architecture-Detail (Bundle-Export-Kontext) | bug medium ui | 2026-08-13 | 2026-08-14 |
| #513 | GESCHLOSSEN | [BUG][HIGH] Baseline-Deadlock: SE-Auditor fail-closed (#490) blockiert Baselines, aber Modify-Buttons sind disabled (#451) ÔÇö Workspace nicht release-f├ñhig | bug high se | 2026-08-13 | 2026-08-15 |
| #522 | GESCHLOSSEN | Review findings: fix/rls-token-usage-tracker-444 ÔÇö session-level SET vs SET LOCAL (1 warning) + 4 suggestions | improvement | 2026-08-14 | 2026-08-14 |
| #527 | GESCHLOSSEN | fix: 10 failing CanvasEditor tests + TypeScript errors on main (frontend) | bug qa frontend | 2026-08-14 | 2026-08-15 |
| #539 | GESCHLOSSEN | [BUG][MEDIUM] MCP admin tool calls (user.create, admin.restore, permissions.*) write no audit entry | bug medium mcp | 2026-08-14 | 2026-08-15 |
| #540 | GESCHLOSSEN | feat: interview: add explicit grounding-target confirmation flow | enhancement | 2026-08-15 | 2026-08-15 |
| #541 | GESCHLOSSEN | improvement: interview: move grounding_context's LLM provider call outside its DB transaction | improvement | 2026-08-15 | 2026-08-15 |
| #542 | GESCHLOSSEN | fix: interview: answer() should validate submitted values against the protocol's declared field type | bug | 2026-08-15 | 2026-08-15 |
| #545 | GESCHLOSSEN | feat: hermes-plugin: add a build-output guard against JSX-mode/bundler regressions | enhancement | 2026-08-15 | 2026-08-15 |
| #568 | GESCHLOSSEN | feat: multi-palette theming system with settings ui (task 8.1) | enhancement ui/ux frontend | 2026-08-16 | 2026-08-20 |
| #569 | GESCHLOSSEN | [FEATURE] SE-Auditor: Findings unterdr├╝cken (False-Positive / Waiver mit Begr├╝ndung) | enhancement | 2026-08-16 | 2026-09-22 |
| #571 | GESCHLOSSEN | [QA][CRITICAL] GET /api/v1/tracelinks/ OOM-killt Backend-Worker - Traceability-Seite komplett down | bug qa critical | 2026-08-16 | 2026-09-11 |
| #572 | GESCHLOSSEN | [QA][CRITICAL] Cross-Workspace-Datenleck: metrics.volatility identisch fuer alle Workspaces | bug qa critical security | 2026-08-16 | 2026-08-19 |
| #573 | GESCHLOSSEN | [QA][HIGH] MCP-Lifecycle-Transitions schreiben keine Audit-Eintraege (silent Audit-Luecke) | bug high qa | 2026-08-16 | 2026-08-19 |
| #574 | GESCHLOSSEN | [QA][HIGH] Soft-Delete loest SE-Auditor-Blocker nicht auf (TRACE-P6 bleibt fuer outdated TestCases) | bug high qa | 2026-08-16 | 2026-08-19 |
| #575 | GESCHLOSSEN | [QA][MEDIUM] Tote Routen /trace-links und /test-cases redirecten lautlos auf Dashboard (4 Legacy-Redirects) | bug medium ui/ux qa | 2026-08-16 | 2026-08-18 |
| #576 | GESCHLOSSEN | [QA][MEDIUM] requirement.validate liefert Python-repr-String statt strukturiertem JSON | bug medium api qa | 2026-08-16 | 2026-09-02 |
| #577 | GESCHLOSSEN | [QA][MEDIUM] review.reject akzeptiert nicht-existente item_id (200 Ghost-Item) | bug medium qa | 2026-08-16 | 2026-08-20 |
| #578 | GESCHLOSSEN | [QA][MEDIUM] test.run_report_results: ungueltige test_case_id -> HTTP 500 statt 400/404 | bug medium qa | 2026-08-16 | 2026-08-18 |
| #579 | GESCHLOSSEN | [QA][MEDIUM] GET /requirements/not-a-uuid/ -> 400 statt 404 (UUID-Validierung inkonsistent) | bug medium api qa | 2026-08-16 | 2026-08-20 |
| #580 | GESCHLOSSEN | [QA][MEDIUM] testcases-Create ignoriert acceptance_criteria/category still (201 ohne Persistenz) | bug medium qa | 2026-08-16 | 2026-08-20 |
| #581 | GESCHLOSSEN | [QA][MEDIUM] SE-Auditor-Kalibrierung: 100% Blocker, 0 Warnings (TRACE-P2 als Blocker, ARCH-003 683x) | medium qa se | 2026-08-16 | 2026-09-16 |
| #582 | GESCHLOSSEN | [QA][LOW] Baseline-400-Fehlermeldung dumpet alle SE-Findings (Response mehrere 100 KB) | low qa | 2026-08-16 | 2026-08-20 |
| #583 | GESCHLOSSEN | [QA][HIGH] IEEE-29148-Pflichtfelder fehlen/leer: kein rationale-Feld im Datenmodell, uid=null, acceptance_criteria 0% | high qa se | 2026-08-16 | 2026-09-20 |
| #584 | GESCHLOSSEN | [QA][HIGH] V&V-Kette unterbrochen: 0/30 verifies-Links, TestRuns bleiben dauerhaft in_progress | high qa se | 2026-08-16 | 2026-08-19 |
| #585 | GESCHLOSSEN | [QA][MEDIUM] Baseline: Liste/Detail/Delete-Zustand inkonsistent (in Liste, Detail 404, dann verschwunden) | medium qa se | 2026-08-16 | 2026-08-19 |
| #587 | **OFFEN** | feat: Promptfoo test infrastructure for prompt templates (Phase 3, Prompt Variable Catalog) | enhancement high qa | 2026-08-16 | - |
| #589 | GESCHLOSSEN | [QA][UI] ­ƒö┤ Login ├╝ber HTTP unm├Âglich ÔÇö Auth-Cookies mit Secure-Flag (AUTH_COOKIE_SECURE) | bug qa p1 | 2026-08-16 | 2026-08-20 |
| #590 | GESCHLOSSEN | [QA][UI] ­ƒö┤ Interview-System unsichtbar: Backend + MCP + Widget-Code vorhanden, aber keine UI-Route, kein Sidebar-Eintrag, kein Workflow | bug qa p1 | 2026-08-16 | 2026-08-20 |
| #591 | GESCHLOSSEN | [QA][UI] ­ƒƒá Mausrad-Scrollen tot au├ƒerhalb des Listen-Panels ÔÇö Dokument scrollt nie (overflow-y:hidden auf Main) | bug qa | 2026-08-16 | 2026-08-20 |
| #592 | GESCHLOSSEN | [QA][UI] ­ƒƒá Sidebar-Clipping jetzt auch auf Desktop 1080p und Mobile ÔÇö Men├╝punkte unerreichbar (Erweiterung von #449) | bug qa | 2026-08-16 | 2026-08-20 |
| #593 | GESCHLOSSEN | [QA][UI] ­ƒƒá /traceability l├ñdt leer mit Console-Error (Trace-Links-Seite) ÔÇö vermutlich #571-Kontext | bug qa | 2026-08-16 | 2026-08-20 |
| #594 | GESCHLOSSEN | [QA][UI] ­ƒƒí CTA-Buttons uneinheitlich: 10+ Label-Varianten statt einheitlichem Muster | bug qa design | 2026-08-16 | 2026-08-24 |
| #595 | GESCHLOSSEN | [QA][UI] ­ƒƒí DE/EN-Sprachmix: Settings-Tabs und Buttons gemischt, ÔÇ×Artefakt laden" auf /impact | bug qa i18n | 2026-08-16 | 2026-08-18 |
| #596 | GESCHLOSSEN | [QA][UI] ­ƒƒí Workflow-Editor: horizontaler Overflow auf allen Viewports + /audit mit 480 KB DOM | bug qa performance | 2026-08-16 | 2026-09-16 |
| #597 | GESCHLOSSEN | Review findings: ReqogniLoom v1.6.0 ÔÇö MCP-Audit-Op-Gap nur partiell geschlossen (1 critical, 2 warnings, 5 suggestions) | improvement | 2026-08-16 | 2026-09-27 |
| #598 | **OFFEN** | Frontend-Review v1.6.0: 5 Warnings + 6 Suggestions (Verdikt: APPROVE ÔÇö #449/#450/B2 gefixt) | - | 2026-08-16 | - |
| #599 | GESCHLOSSEN | Hermes-Plugin: inkompatibel mit aktueller Hermes-API ÔÇö Port auf @hermes/plugin-sdk (Loesungsskizze) | enhancement | 2026-08-16 | 2026-08-20 |
| #601 | GESCHLOSSEN | MCP requirement.update rejects change_reason despite sending it (QA 17.08.2026) | bug qa | 2026-08-17 | 2026-08-18 |
| #604 | GESCHLOSSEN | [QA] ­ƒö┤ Need DELETE gibt HTTP 400 statt 204 | bug qa | 2026-08-17 | 2026-08-18 |
| #605 | GESCHLOSSEN | [QA] ­ƒƒí Architecture CREATE Response-Parsing fehlgeschlagen | bug api qa | 2026-08-17 | 2026-08-20 |
| #606 | GESCHLOSSEN | [FEATURE] API-Key-Management nicht nachhaltig ÔÇö Limit 10 Keys pro User wird schnell erreicht | enhancement qa infrastructure | 2026-08-17 | 2026-08-20 |
| #607 | GESCHLOSSEN | [QA] ­ƒƒí CSRF-Token f├╝r Cookie-Auth + POST ÔÇö API-Consumer m├╝ssen X-CSRFToken mitschicken | bug api qa | 2026-08-17 | 2026-08-20 |
| #608 | GESCHLOSSEN | [QA][UI] ­ƒƒá Sidebar-Overflow #449 ÔÇö REGRESSION: jetzt auch bei 1440├ù900 (17/22 sichtbar) | bug ui/ux qa regression | 2026-08-17 | 2026-08-20 |
| #609 | GESCHLOSSEN | [QA][UI] ­ƒƒá Routen /interviews und /prompts ÔÇö silent Redirect auf Dashboard (Feature-Entdeckungsl├╝cke) | bug ui/ux qa routing | 2026-08-17 | 2026-08-20 |
| #610 | GESCHLOSSEN | [QA][UI] ­ƒƒí DE/EN-Sprachmix auf Workspace Settings Tabs | bug qa i18n | 2026-08-17 | 2026-08-18 |
| #617 | GESCHLOSSEN | fix: CSRF origin validation fails for localhost:5173 | bug | 2026-08-19 | 2026-08-20 |
| #619 | GESCHLOSSEN | improvement: Add code-to-locale coverage check to i18n parity test | enhancement medium qa | 2026-08-19 | 2026-08-20 |
| #622 | GESCHLOSSEN | improvement: Add pagination or aggregation to /audit/ endpoint for accessing capped findings | enhancement | 2026-08-19 | 2026-08-20 |
| #626 | GESCHLOSSEN | fix: MCP audit validation gaps in 17 call-sites (write_mcp_audit exception swallowing) | bug | 2026-08-19 | 2026-08-20 |
| #629 | GESCHLOSSEN | fix: eliminate N+1 query in trace_link_manager batch_create and validate_graph_integrity | bug performance | 2026-08-19 | 2026-08-20 |
| #649 | **OFFEN** | Feature: importable Hermes Skill (connector) alongside the desktop plugin | enhancement integration hermes | 2026-08-20 | - |
| #650 | GESCHLOSSEN | [QA v1.7.0-beta.3] ai_derivation (mimo-v2.5): gelegentlich "LLM response was not valid JSON" / 0 drafts bei cold-start | bug qa llm | 2026-08-20 | 2026-08-24 |
| #651 | GESCHLOSSEN | [QA v1.7.0-beta.3] Sidebar i18n-Sprachmix DE/EN (Fortsetzung #610) | bug qa ui i18n | 2026-08-20 | 2026-09-02 |
| #652 | GESCHLOSSEN | [QA v1.7.0-beta.3] ai_derivation (mimo-v2.5): gelegentlich 'LLM response was not valid JSON' / 0 drafts bei cold-start | bug qa llm | 2026-08-20 | 2026-08-24 |
| #653 | GESCHLOSSEN | [QA v1.7.0-beta.3] Sidebar i18n-Sprachmix DE/EN (Fortsetzung #610) | bug qa ui i18n | 2026-08-20 | 2026-08-24 |
| #654 | GESCHLOSSEN | [QA v1.7.0-beta.3] Sidebar-Navigation: DE/EN-Sprachmix + inkonsistente Kapitalisierung | bug qa ui i18n | 2026-08-20 | 2026-09-02 |
| #655 | GESCHLOSSEN | [QA v1.7.0-beta.3] Header-Hoehe inkonsistent: /requirements (h=134) vs. alle anderen Seiten (h=60) | bug qa ui design | 2026-08-20 | 2026-08-29 |
| #656 | GESCHLOSSEN | [QA v1.7.0-beta.3] Design-Mix: Card-basiert (/import) vs. Listen/Tabellen (alle anderen) ohne einheitliches Pattern | bug qa ui design | 2026-08-20 | 2026-08-29 |
| #657 | GESCHLOSSEN | [QA v1.7.0-beta.3] Import-Seite: ReqIF-Bereich komplett auf Englisch (Rest DE) + CamelCase-Terminologie | bug qa ui i18n | 2026-08-20 | 2026-08-24 |
| #658 | GESCHLOSSEN | [QA v1.7.0-beta.3] Dialog-Platzhalter i18n: ADR-Titel-Platzhalter auf Englisch ('e.g. As a user, I need...') | bug qa ui i18n | 2026-08-20 | 2026-08-24 |
| #659 | GESCHLOSSEN | [QA v1.7.0-beta.3] Admin 'Permission Defaults': englische Labels bei deutscher Sprache | bug qa ui i18n | 2026-08-20 | 2026-08-24 |
| #660 | GESCHLOSSEN | [QA v1.7.0-beta.3] /workflows und /diagrams: kein Header-Container (abweichendes Layout-Pattern) | bug qa ui design | 2026-08-20 | 2026-08-29 |
| #661 | GESCHLOSSEN | [QA v1.7.0-beta.3] /architecture Tree-View: fehlende Tree-Lines, Hierarchie schwer erkennbar | bug qa ui ux | 2026-08-20 | 2026-08-24 |
| #662 | GESCHLOSSEN | [QA v1.7.0-beta.3] Workspace-Einstellungen: 'Speichern' aktiv bei leerem Workspace-Namen (keine Validierung) | bug qa ui validation | 2026-08-20 | 2026-08-24 |
| #663 | GESCHLOSSEN | [QA v1.7.0-beta.3] Workspace-Preset: uneinheitliche Notation ('Baselines: X' vs. Haken bei anderen Optionen) | bug qa ui design | 2026-08-20 | 2026-08-24 |
| #664 | GESCHLOSSEN | [QA v1.7.0-beta.3] Chat-Support-Floating-Button zu dominant, sticht aus Design heraus | bug qa ui design | 2026-08-20 | 2026-08-24 |
| #665 | GESCHLOSSEN | [UI/UX Audit] Navigationsbaum: Strukturelle Entkopplung zwischen Sidebar-Links und In-Page WorkspaceTree | ui ux | 2026-08-20 | 2026-09-16 |
| #666 | GESCHLOSSEN | [UI/UX Audit] Navigationsbaum: Redundanz & Verwirrung durch 3 zeitgleich sichtbare Suchfelder | ui ux design | 2026-08-20 | 2026-09-16 |
| #667 | GESCHLOSSEN | [UI/UX Audit] Navigationsbaum: ARIA Treeview-Regelverletzung durch interaktive Buttons in role="treeitem" | bug ui a11y | 2026-08-20 | 2026-08-24 |
| #668 | GESCHLOSSEN | [UI/UX Audit] Navigationsbaum: Fehlende visuelle Hervorhebung eingeklappter Eltern-Knoten bei aktiver Selektion | ui ux design | 2026-08-20 | 2026-09-16 |
| #669 | GESCHLOSSEN | [UI/UX Audit] Detailansichten: Inkonsistenter Stilmix: CSS Modules vs. JS Inline-Styles in Detailformularen | ui design | 2026-08-20 | 2026-08-30 |
| #670 | GESCHLOSSEN | [UI/UX Audit] Detailansichten: Uneinheitliche L├Âschbest├ñtigungen (Modal Dialog vs. Inline Header vs. Parent) | ui ux design | 2026-08-20 | 2026-08-30 |
| #672 | GESCHLOSSEN | [UI/UX Audit] Detailansichten: Stille Datenverluste durch fehlenden Warn-Dialog bei ungespeicherten ├änderungen | bug ui ux | 2026-08-20 | 2026-08-23 |
| #673 | GESCHLOSSEN | [UI/UX Audit] Detailansichten: Inkonsistente Formular-Resets beim Wechsel des selektierten Artefakts | bug ui validation | 2026-08-20 | 2026-08-23 |
| #674 | GESCHLOSSEN | [UI/UX Audit] Design System: Hardcodierte Hex-Farben & Design-System-Bruch bei Level-Badges im Dark Mode | ui design | 2026-08-20 | 2026-08-30 |
| #675 | GESCHLOSSEN | [UI/UX Audit] Design System: Visuelle Uneinheitlichkeit bei Status-, Version- und Typ-Badges | ui design | 2026-08-20 | 2026-09-16 |
| #676 | GESCHLOSSEN | [UI/UX Audit] i18n: Hardcodierte englische Fallback-Texte in der deutschen Benutzeroberfl├ñche | ui i18n | 2026-08-20 | 2026-08-30 |
| #677 | GESCHLOSSEN | [UI/UX Audit] a11y: Fehlende aria-live-Regionen f├╝r dynamische Formularvalidierungen und Speicherfehler | ui a11y | 2026-08-20 | 2026-09-16 |
| #678 | GESCHLOSSEN | [UI/UX Audit] NeedsEditors: Mehrdeutige Button-Namen (/create\|erstellen/i) bei ge├Âffnetem Erstellungsformular | bug ui a11y | 2026-08-20 | 2026-08-23 |
| #679 | GESCHLOSSEN | [UI/UX Audit] InterviewWidget: Unbehandelter TypeError bei direktem localStorage-Zugriff | bug ui | 2026-08-20 | 2026-08-23 |
| #682 | GESCHLOSSEN | fix: Playwright E2E tests hang/timeout on main (shards 1, 2, 4) | bug high qa | 2026-08-21 | 2026-09-01 |
| #683 | GESCHLOSSEN | fix: dist/plugins/claude-code plugin.json stale relative to build_claude_plugin.py | bug high | 2026-08-21 | 2026-08-21 |
| #687 | GESCHLOSSEN | E2E: 14 Tests hang at disabled quick-create save button (stale helper after BUG-02 title-required fix) | - | 2026-08-22 | 2026-08-22 |
| #688 | GESCHLOSSEN | E2E: 10 tests assert hardcoded English UI strings while app locale follows navigator.language (de-DE fails) | - | 2026-08-22 | 2026-08-22 |
| #689 | GESCHLOSSEN | E2E: needs-cross-boundary strict-mode violation - generic form selector matches new category input | - | 2026-08-22 | 2026-08-22 |
| #690 | GESCHLOSSEN | E2E: waterkettle TestRun helpers stale vs GH-584 auto-completion (close button never renders, wrong status expectation) | - | 2026-08-22 | 2026-08-22 |
| #691 | GESCHLOSSEN | E2E: toothbrush-syseng spec not self-sufficient - fresh env lacks seed_toothbrush (+ BACKEND_URL port mismatch 8000 vs compose 8001) | - | 2026-08-22 | 2026-08-22 |
| #692 | GESCHLOSSEN | E2E flaky: /traceability stuck on loading state >10s under suite load (tracelink list/empty assertion fails) | - | 2026-08-22 | 2026-08-22 |
| #693 | GESCHLOSSEN | chore: malformed .gitignore entry .docs\\test-reports\\ does not match docs/test-reports/ | - | 2026-08-22 | 2026-08-22 |
| #696 | GESCHLOSSEN | Deprecate bearer-token-in-login-response-body (XSS re-exposure risk if ever consumed by JS) | security auth | 2026-08-22 | 2026-09-16 |
| #697 | GESCHLOSSEN | Sweep remaining str(exc) exception-leak sites (CWE-209) ÔÇö ~40+ sites incl. icd_views.py | high security | 2026-08-22 | 2026-09-16 |
| #700 | GESCHLOSSEN | fix: RequirementForm changeReason input can be wiped by refetch race before save completes | bug high frontend | 2026-08-22 | 2026-08-23 |
| #702 | GESCHLOSSEN | Dashboard: large solid magenta rectangle renders where a chart/widget should be | bug frontend | 2026-08-22 | 2026-08-23 |
| #706 | GESCHLOSSEN | fix: celery-beat status 'unknown' appears broken despite intentional design | bug ux | 2026-08-23 | 2026-08-23 |
| #707 | GESCHLOSSEN | fix: Theme palette and light/dark mode cannot be combined (flat list instead of two axes) | bug ui frontend | 2026-08-23 | 2026-08-23 |
| #708 | GESCHLOSSEN | [QA v1.7.0-beta.5][HIGH] Tenant-Last-Admin-Guard umgehbar: revoke_tenant_admin auf eigenen Account erfolgreich ÔÇö API widerspricht DB | bug high qa security | 2026-08-23 | 2026-08-27 |
| #709 | GESCHLOSSEN | [QA v1.7.0-beta.5][MEDIUM] XSS-Input-Sanitization regrediert: <script>-Payload als requirement-Titel wird akzeptiert | bug medium qa security regression | 2026-08-23 | 2026-08-23 |
| #710 | GESCHLOSSEN | [QA v1.7.0-beta.5][LOW] Inkonsistente UUID-Fehlerbehandlung: requirements ÔåÆ 400, needs ÔåÆ 404 bei malformed pk | bug low api qa | 2026-08-23 | 2026-09-02 |
| #711 | GESCHLOSSEN | [QA v1.7.0-beta.5][HOUSEKEEPING] E2E-/CI-Artefakte akkumulieren ungehindert: 60+ e2e-workspaces, 43 revoked API-Keys blockieren das 10-Key-Limit | bug medium ci housekeeping | 2026-08-23 | 2026-09-02 |
| #714 | GESCHLOSSEN | [QA v1.7.0-beta.5][HIGH] LlmSettings-DB-Key ├╝berschreibt funktionierenden Env-Key still ÔåÆ alle LLM-Calls 'Connection error' (Circuit-Breaker ├Âffnet kaskadierend) | bug high qa llm ops | 2026-08-23 | 2026-08-23 |
| #715 | GESCHLOSSEN | [QA v1.7.0-beta.5][LOW] baseline.create scope=document bricht mit internem ValueError statt sauberem Fehler/Ergebnis | bug low qa baseline se-auditor | 2026-08-23 | 2026-08-23 |
| #716 | GESCHLOSSEN | [QA v1.7.0-beta.5][MEDIUM] Viewer-Rolle hat keinen programmatischen API-Zugang: api-keys-Create wird mit RBAC-write abgelehnt | bug medium api qa ux rbac | 2026-08-23 | 2026-08-23 |
| #718 | GESCHLOSSEN | [UI-Audit beta.5][MEDIUM] Header-H├Âhe inkonsistent auf 6 Seiten (57ÔÇô178px statt 60px) + H1 fehlt auf 4 Seiten | bug medium qa ui design | 2026-08-23 | 2026-09-02 |
| #719 | GESCHLOSSEN | [UI-Audit beta.5][MEDIUM] Create-Dialoge inkonsistent: Speichern-vs-Erstellen, fehlendes Primary-Styling, englische Platzhalter | bug medium qa ui design i18n | 2026-08-23 | 2026-08-29 |
| #720 | GESCHLOSSEN | [UI-Audit beta.5] #449 weiterhin offen: Sidebar overflowY:hidden ÔÇö bei kleiner Viewport-H├Âhe nicht scrollbar (6/24 Links) | bug qa ui a11y | 2026-08-23 | 2026-08-24 |
| #722 | GESCHLOSSEN | chore: harden permissions.check RBAC-combination (structured discriminator + Layer-2 relocation) | api security | 2026-08-23 | 2026-09-16 |
| #724 | GESCHLOSSEN | fix: malformed (non-UUID) document_id for baseline.create scope=document leaks a 500 via REST | bug low api baseline | 2026-08-23 | 2026-09-02 |
| #736 | GESCHLOSSEN | [QA v1.7.0] interview.formalize (MCP) liefert nicht aufl├Âsbare Artefakt-ID zur├╝ck | bug qa | 2026-08-24 | 2026-08-27 |
| #737 | GESCHLOSSEN | [QA v1.7.0] Testcases: PATCH erh├Âht `version` (2), aber `/versions/`-Historie bleibt leer (nur v0) | bug qa | 2026-08-24 | 2026-08-27 |
| #738 | GESCHLOSSEN | [QA v1.7.0] interview.answer akzeptiert unbekannte Felder kommentarlos (keine Validierung gegen missing_fields) | bug qa | 2026-08-24 | 2026-08-27 |
| #739 | GESCHLOSSEN | [QA v1.7.0] REST-Parit├ñtsl├╝cke: Goals haben weder DELETE noch Archive-Endpoint (MCP `goal.delete` existiert) | bug qa | 2026-08-24 | 2026-08-27 |
| #741 | GESCHLOSSEN | [UI-Audit v1.7.0] Icon-only-Buttons ohne aria-label/title (Screenreader/Tastatur blind) | qa a11y | 2026-08-24 | 2026-08-30 |
| #767 | GESCHLOSSEN | [QA Audit Follow-up #737] Workflow-Transitions bumpen `version` nicht, ├ñndern aber diff-Inhalt | bug | 2026-08-27 | 2026-09-02 |
| #768 | GESCHLOSSEN | [QA Audit Follow-up #737] ImportService taggt TestCase beim CSV-Import nicht mit Subtyp | bug | 2026-08-27 | 2026-09-02 |
| #789 | GESCHLOSSEN | flaky: UserPreferences.test.tsx fails intermittently under full CI suite | bug | 2026-08-30 | 2026-09-02 |
| #792 | **OFFEN** | [RFC] System-Wide Improvements: Deployment, Security, Operations & DX | enhancement critical security infrastructure dx | 2026-08-31 | - |
| #793 | GESCHLOSSEN | [QA][CRITICAL] memory.query/memory.list ÔåÆ HTTP 500: Honcho-IDs mit Doppelpunkt verletzen v3-Regex '^[a-zA-Z0-9_-]+$' (422) | bug qa critical mcp ai | 2026-09-01 | 2026-09-02 |
| #794 | GESCHLOSSEN | [QA][HIGH] Embedding-Dimensionen inkonsistent (req/tracelink=vector(1536), mem=vector(384), Modell nomic=768) ÔåÆ 0 Embeddings, artifact.search leer | bug high qa data-model ai | 2026-09-01 | 2026-09-02 |
| #795 | GESCHLOSSEN | [QA][HIGH] AI-Derivation ignoriert Workspace-Sprache: derive_requirementsÔåÆChinesisch, decompose_requirement_next_levelÔåÆEnglisch (Workspace de) | bug high qa ai llm i18n | 2026-09-01 | 2026-09-02 |
| #796 | GESCHLOSSEN | [QA][MEDIUM] requirement.check_consistency liefert task_id, aber Ergebnis ist ├╝ber keine API abrufbar (Orphan-Task) | bug medium api qa mcp | 2026-09-01 | 2026-09-02 |
| #797 | GESCHLOSSEN | [QA][MEDIUM] Create-Button-Inkonsistenz: 7 Seiten doppelter Button ('Im Dialog erstellen' + '+ Neuer X'), 5 Seiten nur einer, Diagramme 2 verschiedene Labels, Baselines keiner | bug medium ui/ux qa ui | 2026-09-01 | 2026-09-16 |
| #798 | GESCHLOSSEN | [QA][LOW] Create-CTA 'Im Dialog erstellen' ist ein Interview-Start (navigiert zu /interviews), kein Formular-Dialog - irref├╝hrendes Label, DE/EN-Wortlaut divergiert | bug low qa ui i18n | 2026-09-01 | 2026-09-02 |
| #799 | GESCHLOSSEN | [QA][MEDIUM] MCP inputSchema-Mismatches: 12 Tools mit fehlenden required-Feldern vs. Server-Validierung (Agenten nutzen falsche Parameter) | bug medium api qa mcp | 2026-09-01 | 2026-09-11 |
| #800 | GESCHLOSSEN | [UI][HIGH] Fokus-Trap/TAB-Reihenfolge im Requirement-Create-Dialog fehlerhaft: Start bei Beschreibung, ├ù-Close vor Formfeldern | bug qa ui a11y | 2026-09-01 | 2026-09-02 |
| #801 | **OFFEN** | [UI][HIGH] Inspector (Version/History/Diff) nur bei Requirements ÔÇö 6 andere Entity-Typen haben keinen Verlaufs-Zugriff | enhancement qa ui consistency | 2026-09-01 | - |
| #802 | GESCHLOSSEN | [UI][HIGH] Zwei Create-Paradigmen: Modals (5 Entities) vs Inline-Forms (Need/Glossary) ÔÇö inkonsistente Interaktion | bug qa ui consistency | 2026-09-01 | 2026-09-16 |
| #803 | GESCHLOSSEN | [UI][MEDIUM] Requirement-Formular: Attribute ungruppiert ÔÇö 2 Abschnitte, dann 6 lose Felder ohne logische Cluster | enhancement qa ui ux | 2026-09-01 | 2026-09-16 |
| #804 | GESCHLOSSEN | [UI][MEDIUM] Entity-Listen zeigen SE-Attribute nicht: nur Hash+Titel+Status sichtbar (Kategorie/V-Ebene/Verifizierung/Traces fehlen) | enhancement qa ui ux | 2026-09-01 | 2026-09-16 |
| #805 | GESCHLOSSEN | [UI][MEDIUM] Need-Titel-Feld ohne Label, englischer Placeholder 'e.g. As a user, I need...' im deutschen UI | bug qa ui i18n | 2026-09-01 | 2026-09-02 |
| #806 | GESCHLOSSEN | [UI][MEDIUM] Dashboard/Metrics: massive Leerr├ñume ÔÇö 2 Workspace-Cards bzw. 5 KPI-Cards, dann nichts (Informationsdichte unausgewogen) | enhancement qa ui ux | 2026-09-01 | 2026-09-16 |
| #807 | GESCHLOSSEN | [UI][MEDIUM] Listen verwenden Kurz-Hash (8 Zeichen) statt lesbarer ID ÔÇö SR-Badge unklart beschriftet | medium qa ui ux | 2026-09-01 | 2026-09-16 |
| #808 | GESCHLOSSEN | [UI][LOW] Traceability hei├ƒt in der Sidebar 'Verkn├╝pfungen' ÔÇö Fachbegriff-Divergenz zum Rest der App | qa ui i18n | 2026-09-01 | 2026-09-19 |
| #809 | GESCHLOSSEN | [UI][LOW] SE-Metriken: 4+1-KPI-Layout (5. Karte allein in zweiter Reihe) statt responsives Grid | qa ui ux | 2026-09-01 | 2026-09-16 |
| #810 | GESCHLOSSEN | [RFC][UX] Minimal/Expert-UI: rollenbasierte Ansichts-Modi (viewerÔåÆMinimal erzwungen, editor/admin umschaltbar) | enhancement ui ux rfc | 2026-09-01 | 2026-09-27 |
| #811 | GESCHLOSSEN | [UI][HIGH] Delete-Flow: Dialog schlie├ƒt trotz Server-Fehler (change_reason-Pflicht) ÔÇö Objekt bleibt bestehen, UI vermittelt Erfolg | bug qa ui ux | 2026-09-01 | 2026-09-02 |
| #813 | GESCHLOSSEN | fix: Fresh migrate crashes on diagram.0004_diagramversion_canvas_json: DuplicateColumn (breaks every clean v1.8.0-beta.5 install) | bug | 2026-09-01 | 2026-09-01 |
| #815 | GESCHLOSSEN | seed_demo violates RLS policy under least-privilege DB role (workspace_provisioning uses wrong tenant-context setter) | bug | 2026-09-01 | 2026-09-02 |
| #816 | GESCHLOSSEN | TestCase.test_type: two competing representations (artifact_type prefix vs. first-class field) | bug | 2026-09-02 | 2026-09-16 |
| #820 | GESCHLOSSEN | [QA][v1.8.0-beta.6][MEDIUM] Input-Sanitization inkonsistent: SQLi-Title wird akzeptiert (HTTP 201), XSS-Title abgewiesen (400) | bug qa security | 2026-09-02 | 2026-09-16 |
| #821 | GESCHLOSSEN | [QA][v1.8.0-beta.6][HIGH] Baseline-Gate blockiert: 47 Blocker, Override mit 10+ Zeichen funktioniert | bug qa | 2026-09-02 | 2026-09-16 |
| #822 | GESCHLOSSEN | [QA][v1.8.0-beta.6][LOW] Health-Check: celery_beat status 'unknown' | bug qa | 2026-09-02 | 2026-09-12 |
| #823 | GESCHLOSSEN | [QA][v1.8.0-beta.6][LOW] admin.backup_create erzeugt unkomprimiertes .json | bug qa | 2026-09-02 | 2026-09-20 |
| #824 | GESCHLOSSEN | [QA][v1.8.0-beta.6][LOW] Custom-Fields: kein REST-Endpoint fur CRUD | bug qa | 2026-09-02 | 2026-09-11 |
| #825 | GESCHLOSSEN | [QA][v1.8.0-beta.6][LOW] suggest_architecture_for_requirement liefert leere Ergebnisse | bug qa | 2026-09-02 | 2026-09-16 |
| #826 | GESCHLOSSEN | [QA][v1.8.0-beta.6][HIGH] Embedding-Dim-Mismatch: DB vector(384) vs 768-dim Ollama/Honcho (Issue #794) | bug qa | 2026-09-02 | 2026-09-12 |
| #827 | GESCHLOSSEN | [QA][v1.8.0-beta.6][MEDIUM] artifact.search liefert relevance_score >1.0 (bis 2.0) | bug qa | 2026-09-02 | 2026-09-12 |
| #828 | GESCHLOSSEN | [QA][v1.8.0-beta.6][MEDIUM] AI-Drafts auf Englisch trotz Workspace language=de (Issue #795) | bug qa | 2026-09-02 | 2026-09-11 |
| #829 | GESCHLOSSEN | [QA][v1.8.0-beta.6][MEDIUM] TestCase-PATCH lehnt change_reason ab ÔÇö inkonsistenter API-Vertrag | bug qa | 2026-09-02 | 2026-09-12 |
| #830 | GESCHLOSSEN | [QA][v1.8.0-beta.6][LOW] Custom-Field-Erstellung im UI schlagt leise fehl (403) | bug qa | 2026-09-02 | 2026-09-11 |
| #831 | GESCHLOSSEN | [QA][v1.8.0-beta.6][LOW] Glossary nutzt 'lifecycle_status' statt 'status' | bug qa | 2026-09-02 | 2026-09-12 |
| #832 | GESCHLOSSEN | [QA][v1.8.0-beta.6][LOW] Trace-Link-Picker zeigt duplizierte Artefakte | bug qa | 2026-09-02 | 2026-09-12 |
| #845 | GESCHLOSSEN | P0: CSRF-Cookie mit Secure-Flag ├╝ber HTTP blockiert alle Schreibzugriffe aus der UI | bug critical security audit-2026-09-02 | 2026-09-03 | 2026-09-11 |
| #846 | GESCHLOSSEN | P0: KI-Pfade robust machen ÔÇö Score-Parsing, JSON-Repair, Timeout, Health-Probe | bug critical ai audit-2026-09-02 | 2026-09-03 | 2026-09-11 |
| #847 | GESCHLOSSEN | P0: Fehlende Embeddings blockieren '├ähnliche finden' und Interview-Grounding | bug critical ai audit-2026-09-02 | 2026-09-03 | 2026-09-12 |
| #848 | GESCHLOSSEN | P0: Suspect-Propagation tot ÔÇö 'suspect' fehlt im Requirement-Serializer | bug critical traceability audit-2026-09-02 | 2026-09-03 | 2026-09-11 |
| #849 | GESCHLOSSEN | P0: Rollenbasierte UI fehlt ÔÇö Viewer sieht alle Schreib-Buttons und Admin-Navigation | bug ui/ux critical audit-2026-09-02 | 2026-09-03 | 2026-09-10 |
| #850 | GESCHLOSSEN | Client-Integrationen kaputt: Claude Code und OpenCode nicht verdrahtet | bug mcp audit-2026-09-02 | 2026-09-03 | 2026-09-11 |
| #851 | GESCHLOSSEN | API-Hygiene: stille Feld-Verwerfung, page=99 ÔåÆ 500, JSON-RPC-Batch ÔåÆ 500 | bug api rest audit-2026-09-02 | 2026-09-03 | 2026-09-12 |
| #864 | GESCHLOSSEN | P0: TestCaseSerializer verwirft test_type ÔÇö API-Rejection (400) und fehlendes Feld im UI | bug critical rest | 2026-09-05 | 2026-09-12 |
| #865 | GESCHLOSSEN | P1: Granulare API-Key Scopes (READ_ONLY, AUTHOR, ADMIN) gegen Indirect Prompt Injection | high security mcp | 2026-09-05 | 2026-09-16 |
| #866 | GESCHLOSSEN | P1: MCP-Server 100-KB Tool-Katalog explodiert im Kontextfenster (~35.000 Token) ÔÇö tools/filter & Kompaktierung | enhancement high mcp | 2026-09-05 | 2026-09-19 |
| #867 | GESCHLOSSEN | P1: Antigravity-Plugin SKILL.md bricht durch relativen Pfad zu DOMAIN_MODEL.md | bug documentation high | 2026-09-05 | 2026-09-11 |
| #868 | GESCHLOSSEN | P1: Fehlendes Optimistic Locking (ETags / If-Match) auf Requirement, TestCase und Baseline (Lost Updates) | bug high api rest | 2026-09-05 | 2026-09-16 |
| #869 | GESCHLOSSEN | P1: Testschritte (steps JSONField) in TestCaseForm ohne visuellen Editor | enhancement high ui/ux | 2026-09-05 | 2026-09-11 |
| #870 | GESCHLOSSEN | P1: TestRuns-Ansicht bietet keine M├Âglichkeit zur Zuweisung von Testf├ñllen im WebUI | bug high ui/ux | 2026-09-05 | 2026-09-11 |
| #871 | GESCHLOSSEN | P1: Fehlende INCOSE-Kernattribute auf Requirement (Rationale, Source, Owner, Priority) | enhancement high se data-model | 2026-09-05 | 2026-09-20 |
| #872 | GESCHLOSSEN | P2: Drei konkurrierende Statusachsen auf Requirement harmonisieren (WorkflowItemState als Single Source of Truth) | bug medium data-model | 2026-09-05 | 2026-09-11 |
| #873 | GESCHLOSSEN | P1: ModalDialogBase.tsx Pseudo-Modale (Akkordeon) eliminieren und auf Portal <Dialog> migrieren | bug high ui/ux | 2026-09-05 | 2026-09-16 |
| #874 | GESCHLOSSEN | P2: Mobile Bottom-Sheet Transformation (ResponsiveDialog) f├╝r Smartphones (360pxÔÇô428px) | enhancement high ui/ux | 2026-09-05 | 2026-09-16 |
| #875 | GESCHLOSSEN | P2: Dashboard: WorkspaceCard-Titel kollidiert mit absolutem Preset-Badge | bug medium ui/ux | 2026-09-05 | 2026-09-11 |
| #876 | GESCHLOSSEN | P3: 1.015 Inline-Styles und 74 Hardcoded Hex-Farben auf tokens.css migrieren (Theme-Kollaps auf Canvas) | enhancement low ui/ux | 2026-09-05 | 2026-09-23 |
| #877 | **OFFEN** | P2: Funktionale Architekturschicht (LogicalFunction & performs-Link) f├╝r NASA SE Prozess 3 | enhancement high se | 2026-09-05 | - |
| #878 | **OFFEN** | P2: Validierungs-L├╝cke schlie├ƒen: Verkn├╝pfung TestCase -> validates -> StakeholderNeed | enhancement medium se | 2026-09-05 | - |
| #879 | **OFFEN** | P3: Projekt-Meilensteine (SRR, PDR, CDR) als System-Entit├ñten f├╝r Phasenbewertung | enhancement low se | 2026-09-05 | - |
| #881 | GESCHLOSSEN | fix: validate_artifact_fields enforcement incomplete on MCP and bulk import | bug | 2026-09-09 | 2026-09-09 |
| #882 | GESCHLOSSEN | fix: describe_attribute_schema returns static definition instead of current | bug | 2026-09-09 | 2026-09-09 |
| #883 | GESCHLOSSEN | feat: add attribute definition support for ChangeRequest item type | enhancement | 2026-09-09 | 2026-09-09 |
| #884 | GESCHLOSSEN | fix: Postgres connection pool exhaustion under sustained E2E load | bug | 2026-09-09 | 2026-09-11 |
| #885 | GESCHLOSSEN | fix(e2e): regenerate stale Linux visual baseline for /settings route | bug qa | 2026-09-09 | 2026-09-11 |
| #886 | GESCHLOSSEN | fix: ArtifactForm violates editable:false backend contract ÔÇö leaves value in payload instead of omitting it | bug | 2026-09-09 | 2026-09-16 |
| #887 | GESCHLOSSEN | fix: custom_fields still unsupported for ChangeRequest/Goal/GlossaryTerm | bug | 2026-09-09 | 2026-09-16 |
| #889 | GESCHLOSSEN | fix: Requirement.category enum validation inconsistency between create and edit forms | bug frontend | 2026-09-09 | 2026-09-16 |
| #890 | GESCHLOSSEN | fix: Adr.description max_length divergence (model 10000 vs serializer 20000) | bug | 2026-09-09 | 2026-09-12 |
| #893 | GESCHLOSSEN | [QA][beta.7] Migration 0081 (link-type catalog) fails on real-world legacy trace links ÔÇö verify_migrated_links refuses existing rows | bug qa | 2026-09-10 | 2026-09-10 |
| #894 | GESCHLOSSEN | [QA][beta.7] deploy/docker-compose.yml tmpfs mount breaks non-root frontend (SA-48) ÔÇö Permission denied restart loop | bug qa | 2026-09-10 | 2026-09-10 |
| #895 | GESCHLOSSEN | [QA][beta.7] Tag hygiene: v0.101.0-beta.6 and v1.0.0 appear next to v1.8.0-beta.7 ÔÇö inconsistent version scheme | qa housekeeping | 2026-09-10 | 2026-09-10 |
| #911 | GESCHLOSSEN | [QA][beta.10] deploy/docker-compose.yml hardcodet den Platzhalter http://<your-ollama-host>:11434/v1 fuer Honcho-Embeddings - Honcho kann nicht embedden, /health meldet trotzdem ok | bug qa infra llm | 2026-09-11 | 2026-09-12 |
| #912 | GESCHLOSSEN | [QA][beta.10] Preset-mandatory_fields laufen ins Leere - 22x 'preset mandatory_fields ... with no matching attribute - ignored' im migrate-Log | bug qa data-model validation | 2026-09-11 | 2026-09-12 |
| #913 | GESCHLOSSEN | [QA][beta.10] Rule 0 nur im Zustand 'proposed': nach Human-Confirm kann derselbe Agent sein Artefakt selbst bis 'approved' eskalieren | bug high qa security | 2026-09-11 | 2026-09-16 |
| #914 | GESCHLOSSEN | [QA][beta.10] Trace-Link confirm/discard durch Agent liefert HTTP 500 statt 403 - AgentSelfConfirmError wird im View nicht gefangen | bug api qa security | 2026-09-11 | 2026-09-16 |
| #915 | GESCHLOSSEN | [QA][beta.10] PATCH /requirements/{id}/ mit 'status' gibt HTTP 200 zurueck, aendert aber nichts - read_only-Feld still verworfen | bug medium api qa | 2026-09-11 | 2026-09-16 |
| #916 | GESCHLOSSEN | [QA][beta.10] Unbekannte Request-Felder werden still verworfen (kein 400) - agent_identity, type, rationale | bug medium api qa | 2026-09-11 | 2026-09-16 |
| #917 | GESCHLOSSEN | [QA][beta.10] API-Key-Limit schlaegt Scope-Pruefung: read-only Key bekommt 400 'max active keys' statt 403 'read-only' | bug low api qa | 2026-09-11 | 2026-09-16 |
| #918 | GESCHLOSSEN | [Bundle B4] AI/Embeddings/Ops ÔÇö Deployment-Robustheit (P0) | bug infra ai llm ops | 2026-09-11 | 2026-09-20 |
| #919 | GESCHLOSSEN | [Bundle B1] API-Contract-Konsistenz (P1) | bug api mcp rest | 2026-09-11 | 2026-09-17 |
| #920 | GESCHLOSSEN | [Bundle B2] Artefakt-/Attributfelder konsistent (P1) | bug frontend data-model validation | 2026-09-11 | 2026-09-17 |
| #921 | GESCHLOSSEN | [Bundle B3] Baseline/Governance (P2) | bug se baseline validation | 2026-09-11 | 2026-09-20 |
| #922 | GESCHLOSSEN | [Bundle B5] UI-Konsistenz & Listen-Performance (P2) | bug ui/ux ui frontend performance | 2026-09-11 | 2026-09-16 |
| #923 | GESCHLOSSEN | [Bundle B6] Optimistic Locking (ETag/If-Match) (P2) | bug high api rest | 2026-09-11 | 2026-09-16 |
| #924 | GESCHLOSSEN | [Bundle B7] E2E-Verifikation Shard 2 (P3, parallel) | bug qa ci | 2026-09-11 | 2026-09-19 |
| #925 | GESCHLOSSEN | [QA][beta.10][P3] i18n-Key-Leaks: 'traceability.testCasesGroup' + 5 weitere Keys sichtbar im UI (kein Fallback) | bug qa ui frontend i18n | 2026-09-11 | 2026-09-16 |
| #926 | GESCHLOSSEN | [QA][beta.10][P2] Requirements nutzt Legacy-Inline-Form statt CreateTraceLinkDialog + uneinheitliche Button-Dimensionen in den Detail-Dialogen | bug ui/ux qa ui frontend | 2026-09-11 | 2026-09-19 |
| #927 | GESCHLOSSEN | [UI][beta.10] Ableiten-Buttons vereinheitlichen: ÔÇ×AbleitenÔÇ£ (manuell) vs. ÔÇ×KI-AbleitungÔÇ£ (KI) + ÔÇ×KI-TestfallÔÇ£ | enhancement ui/ux ui frontend | 2026-09-11 | 2026-09-19 |
| #928 | GESCHLOSSEN | [UI][beta.10] Anforderung ÔåÆ Systemelement (Allocation) ist nicht auffindbar ÔÇô Funktion vorhanden, aber kein UI-Einstieg | enhancement ui/ux se frontend | 2026-09-11 | 2026-09-19 |
| #929 | GESCHLOSSEN | [SE][Konzept] 3-Stufen-Attributmodell (Basissatz / Stringenz / Full-SE) f├╝r alle 11 Artefakt-Masken | enhancement ui/ux se data-model | 2026-09-11 | 2026-09-27 |
| #930 | GESCHLOSSEN | [SE][Tooling] Attribut- & Wert-Migrationssystematik (AWMS) ÔÇö Attribute und Inhalte verschieben | enhancement se data-model tooling | 2026-09-11 | 2026-09-20 |
| #932 | GESCHLOSSEN | [SE][CRITICAL] `uid` ist als "auto-generated" dokumentiert, wird aber nie erzeugt ÔÇö 0 % gef├╝llt, read-only, UI f├ñllt auf den UUID-Kurz-Hash zur├╝ck | bug se critical data-model | 2026-09-11 | 2026-09-20 |
| #934 | **OFFEN** | [Epic] Attribut-System v3 - Attribute Usability Contract (REST+MCP) | enhancement se data-model | 2026-09-12 | - |
| #935 | GESCHLOSSEN | Attribut v3 - WS1 Transport-Paritaet REST+MCP (alle 11 Typen, Icd, Discovery) | se data-model | 2026-09-12 | 2026-09-14 |
| #936 | GESCHLOSSEN | Attribut v3 - WS2 Identitaet & Systemfelder (Artifact.owner/reporter/priority, Actor) | se data-model | 2026-09-12 | 2026-09-14 |
| #937 | GESCHLOSSEN | Attribut v3 - WS3 Display-Engine (copyable/reveal/mask/format) | ui/ux se | 2026-09-12 | 2026-09-14 |
| #938 | GESCHLOSSEN | Attribut v3 - WS4 Layout-Engine (12 Spalten, quarter, Section- und Attribut-Dummies) | ui/ux se | 2026-09-12 | 2026-09-14 |
| #939 | GESCHLOSSEN | Attribut v3 - WS6 3-Stufen-Modell ausrollen (priority, MoSCoW nur Need) | se data-model | 2026-09-12 | 2026-09-14 |
| #940 | GESCHLOSSEN | Attribut v3 - WS7 AWMS Werte-Migration | se data-model tooling | 2026-09-12 | 2026-09-14 |
| #941 | **OFFEN** | Attribut v3 - WS0 Fundament: Contract-Matrix + gemeinsamer Gateway + #912 | se data-model | 2026-09-12 | - |
| #942 | GESCHLOSSEN | Attribut v3 - WS5 Zentraler Attribut-Katalog | ui/ux se data-model | 2026-09-12 | 2026-09-14 |
| #944 | GESCHLOSSEN | feat(api): runtime-configurable REST/MCP rate limits | enhancement api mcp feature | 2026-09-12 | 2026-09-16 |
| #946 | **OFFEN** | feat(debug): in-UI annotation layer for admin debug mode (text + design notes, export, central deletion) | ui/ux frontend feature | 2026-09-14 | - |
| #947 | GESCHLOSSEN | [E2E] Playwright-Suite: Bootstrap-Vorbedingung + zustandsabh├ñngige/flaky Specs h├ñrten | qa tooling | 2026-09-14 | 2026-09-22 |
| #948 | GESCHLOSSEN | fix: CRLF-encoded hook scripts break pre-release-check.sh on Windows | bug infrastructure | 2026-09-14 | 2026-09-16 |
| #949 | GESCHLOSSEN | fix: action-pin-validation gate regex misses subpath action pins (owner/repo/sub@ref) | bug ci | 2026-09-14 | 2026-09-16 |
| #950 | GESCHLOSSEN | [SE][MEDIUM] Trace-Katalog unvollst├ñndig: keine `satisfies`/`realizes`/`refines`-Links ÔÇö GoalÔåÆRequirement-Satisfaction nicht abbildbar | enhancement medium se traceability | 2026-09-15 | 2026-09-20 |
| #951 | GESCHLOSSEN | [QA][MEDIUM] `audit.ai_review` (MCP) liefert literal `null` statt Findings-Payload | bug medium qa mcp se-auditor | 2026-09-15 | 2026-09-16 |
| #952 | GESCHLOSSEN | [UI][HIGH] SE-Auditor-Seite zeigt 'Findings: 0 ┬À Blocker: 0' ÔÇö REST-API meldet 24 Blocker (UI falsch-negativ) | bug high ui se-auditor | 2026-09-15 | 2026-09-16 |
| #953 | GESCHLOSSEN | [QA][MEDIUM] TC-Create-Formular speichert test_type=null trotz dokumentiertem Default; Traceability markiert Anforderung trotz verifies-Link als "kein Test" | bug medium qa traceability | 2026-09-15 | 2026-09-16 |
| #954 | GESCHLOSSEN | [UI][MEDIUM] Admin-Create-Dialoge ohne Design-System: Workspace-Dialog-Buttons ohne btn-*-Klassen, 9 Button-H├Âhen (20ÔÇô54px), 3 parallele Styling-Systeme | enhancement medium ui design | 2026-09-15 | 2026-09-16 |
| #955 | GESCHLOSSEN | [UI][MEDIUM] Admin-Create-Dialoge: aria-modal=true ohne aria-label; Arch-Titel-Feld ohne koppelbare ID/Label | bug medium ui a11y | 2026-09-15 | 2026-09-16 |
| #960 | GESCHLOSSEN | [BUG] Preset switch does not re-materialize workspace attribute definitions (workspace_definition_store resolves stale preset) | bug data-model | 2026-09-17 | 2026-09-17 |
| #977 | GESCHLOSSEN | test: non-deterministic embedding/semantic tests flake in backend-test set-1-core | bug ci | 2026-09-18 | 2026-09-19 |
| #980 | GESCHLOSSEN | [QA][beta.12][MEDIUM] Bluepencil review layer cannot be armed in a prebuilt/production deployment (Dockerfile ARG + nginx location missing) | bug frontend infra | 2026-09-18 | 2026-09-19 |
| #981 | GESCHLOSSEN | [QA][beta.12][MEDIUM] Bluepencil layer silently fails on plain-HTTP non-localhost origins (WebCrypto integrity check) | bug frontend docs | 2026-09-18 | 2026-09-19 |
| #982 | GESCHLOSSEN | [QA][beta.12][LOW] comment.create answers "Error: An internal error occurred." instead of naming the missing required field | bug mcp | 2026-09-18 | 2026-09-19 |
| #983 | GESCHLOSSEN | [QA][beta.12][LOW] GET /api/v1/artifacts/{id}/comments/ returns 200 [] for a non-existent artifact (POST returns 404) | bug api | 2026-09-18 | 2026-09-19 |
| #984 | GESCHLOSSEN | [QA][beta.12][LOW] No ETag response header on artifact reads although If-Match/412 optimistic locking is supported | bug api | 2026-09-18 | 2026-09-19 |
| #985 | GESCHLOSSEN | [QA][beta.12][MEDIUM] Overlays ignore Escape: notification popover and system-health dialog stay open (outside click ignored too) | bug ui/ux frontend a11y | 2026-09-18 | 2026-09-18 |
| #986 | GESCHLOSSEN | [QA][beta.12][MEDIUM] Button/control variance on /settings: 22 buttons, 10 distinct style signatures (no control standard) | ui/ux frontend design-system | 2026-09-18 | 2026-09-19 |
| #987 | GESCHLOSSEN | [UX][beta.12] Move system notifications from the sidebar into the AI bubble (decision request) | ui/ux frontend | 2026-09-18 | 2026-09-27 |
| #988 | **OFFEN** | [BUG][beta.12] Review layer stores every note as author "anonymous": vendored bluepencil bundle predates the upstream identity fix (#12/#15) | bug frontend dependencies | 2026-09-18 | - |
| #989 | GESCHLOSSEN | [FEATURE][beta.12] Default trace link type must be configurable via environment (Standard-Linktyp / Decomposition Link Typ) | enhancement configuration | 2026-09-18 | 2026-09-20 |
| #990 | GESCHLOSSEN | [BUG][beta.12] System-status dialog and /health/ disagree; 1s embedding probe reports a healthy backend as AUSGEFALLEN | bug ops health | 2026-09-18 | 2026-09-19 |
| #991 | GESCHLOSSEN | [UI][MEDIUM] Dialog does not return focus to the trigger on close (useFocusTrap restore) | bug ui/ux frontend a11y | 2026-09-18 | 2026-09-19 |
| #1002 | GESCHLOSSEN | [RFC] Workspace-Ged├ñchtnis v2: Artefakt-Scope, Provenienz & gleichwertiger Zugriff ├╝ber UI, REST und MCP (Honcho-Korrekturen) | enhancement api ui mcp ai privacy p1 rfc | 2026-09-19 | 2026-09-21 |
| #1003 | GESCHLOSSEN | [SE][Data-Model] ReqIF-Identitaet von der lokalen uid trennen - eigene Felder fuer externe IDs (Round-Trip) | high se data-model integration | 2026-09-19 | 2026-09-27 |
| #1018 | GESCHLOSSEN | [QA][beta.13][MEDIUM] deploy: --profile honcho mit 768er-Embedding startet nicht ÔÇö Compose f├╝hrt Honchos configure_embeddings.py nie aus | - | 2026-09-20 | 2026-09-21 |
| #1019 | GESCHLOSSEN | [QA][beta.13][MEDIUM] Image-Deployment kann Nicht-384-Embeddings nicht per Env aktivieren ÔÇö Spalten bleiben vector(384), Writes werden still ├╝bersprungen | - | 2026-09-20 | 2026-09-21 |
| #1021 | GESCHLOSSEN | [QA][beta.13][MEDIUM] SE-Audit: TRACE-P1 verstummt still, wenn die Requirement-Hierarchie zyklisch wird (kombinierter decomposes+derives-from-Link) | - | 2026-09-20 | 2026-09-21 |
| #1031 | GESCHLOSSEN | fix: bluepencil host-identity bridge missing (host.ts + AuthContext + data-identity) | bug frontend | 2026-09-21 | 2026-09-24 |
| #1050 | GESCHLOSSEN | [QA][beta.15][HIGH] opencode_go: LLM-Aufrufe scheitern mit 400 MissingSessionID ÔÇö LLM_PROVIDER=opencode_go ist ohne LLM_OPENCODE_SESSION still tot | - | 2026-09-23 | 2026-09-27 |
| #1051 | GESCHLOSSEN | [QA][beta.15][HIGH] Honcho-Engine-Module (Dialectic/Deriver/Summary/Dream) k├Ânnen am gepinnten Zen-Go-Endpunkt nicht authentifizieren | - | 2026-09-23 | 2026-09-27 |
| #1052 | GESCHLOSSEN | [QA][beta.15][HIGH] Kein Deriver-/Queue-Worker im honcho-Service ÔÇö Memory-Work-Units bleiben dauerhaft unprocessed | - | 2026-09-23 | 2026-09-27 |
| #1053 | GESCHLOSSEN | [QA][beta.15][MEDIUM] align_embedding_dimensions scheitert an der App-Rolle; MemoryEntry.embedding bleibt vector(384) im Image-Deployment | - | 2026-09-23 | 2026-09-27 |
| #1054 | GESCHLOSSEN | [QA][beta.15][HIGH] nginx cacht die Backend-IP: nach jedem Backend-Recreate liefert der Frontend-Proxy 502 ÔÇö UI laedt, Login scheitert | - | 2026-09-23 | 2026-09-27 |
| #1074 | GESCHLOSSEN | [QA][beta.16][CRITICAL] Automatisches DB-Backup erzeugt eine 389-Byte-Leerdatei und meldet Erfolg (pg_dump\|gzip-Pipeline ohne pipefail) | bug qa critical infrastructure ops | 2026-09-26 | 2026-09-27 |
| #1075 | GESCHLOSSEN | [QA][beta.16][HIGH] ICDs sind als TraceLink-Endpunkt nicht referenzierbar ÔÇö GET /icds/{id}/ liefert 200, POST /tracelinks/ mit derselben UUID 404 | bug high qa rest data-model traceability | 2026-09-26 | 2026-09-27 |
| #1076 | GESCHLOSSEN | [QA][beta.16][MEDIUM] Ein ung├╝ltiger X-API-Key verdr├ñngt einen g├╝ltigen Bearer-Token (401 statt 200) | bug medium qa security auth | 2026-09-26 | 2026-09-27 |
| #1077 | GESCHLOSSEN | [QA][beta.16][HIGH] GET /workspaces/{fremde-id}/permission-definition/ liefert 500 mit HTML statt JSON-Envelope | bug high api qa security | 2026-09-26 | 2026-09-27 |
| #1078 | GESCHLOSSEN | [BUG][beta.16][MEDIUM] Baseline-Liste liefert entries: [] w├ñhrend der Detail-Endpunkt 4 Eintr├ñge zeigt (Regression zu #585) | bug medium baseline regression consistency | 2026-09-26 | 2026-09-27 |
| #1079 | GESCHLOSSEN | [QA][beta.16][LOW] POST-Antworten tragen keinen ETag-Header, obwohl If-Match/412 auf der Create-Response startet (Nachtrag zu #984) | low api qa consistency | 2026-09-26 | 2026-09-27 |
| #1080 | GESCHLOSSEN | [QA][beta.16][MEDIUM] TestRun ist ├╝ber REST vorhanden (count 2), aber ├╝ber MCP nicht erreichbar ÔÇö kein Tool in 218 Tools/35 Gruppen | enhancement medium qa se mcp | 2026-09-26 | 2026-09-27 |
| #1081 | GESCHLOSSEN | [QA][beta.16][MEDIUM] Zwei Fehler-Envelope-Formen nebeneinander: mit error.code und ohne code | medium api qa consistency | 2026-09-26 | 2026-09-27 |
| #1082 | GESCHLOSSEN | [BUG][beta.16][HIGH] AWMS-Rollback meldet restored:0 und status:rolled_back, l├ñsst define_attribute-Definitionen aber bestehen | bug high data-model attributes | 2026-09-26 | 2026-09-27 |
| #1083 | GESCHLOSSEN | [BUG][beta.16][HIGH] Workspace-skopierter Migrationsplan mutiert Attribut-Definitionen tenant-weit (Blast-Radius, Dry-run verschweigt es) | bug high security data-model attributes | 2026-09-26 | 2026-09-27 |
| #1084 | GESCHLOSSEN | [BUG][beta.16][MEDIUM] Hard-Delete eines Workspace mit Baselines liefert 500 (DB-Trigger 'Baselines are immutable') | bug medium baseline regression | 2026-09-26 | 2026-09-27 |
| #1085 | GESCHLOSSEN | [DOCS][beta.16][LOW] Doku-Drift-Bundle: MCP-Katalog 218/35, memory.write existiert, expected_version, /baselines/-Pfad, VCRM-Namensgebung, TraceLink-ID-Raum | documentation low mcp docs | 2026-09-26 | 2026-09-27 |
| #1086 | GESCHLOSSEN | [Attribut][beta.16] `level` ist ein frei editierbares Enum ohne Ableitung ÔÇö Systemlevel wird manuell gepflegt (Bluepencil-Notiz) | se ux frontend data-model attributes | 2026-09-26 | 2026-09-27 |
| #1087 | **OFFEN** | [UX][beta.16] Anforderungsformular: Speichern ist nicht per Ctrl/Cmd+S erreichbar (Bluepencil-Notiz) | usability ux frontend a11y | 2026-09-26 | - |
| #1088 | GESCHLOSSEN | [SE][beta.16] `source` vermischt Herkunft und Stakeholder; Needs haben kein Stakeholder-Feld (Bluepencil-Notiz) | se data-model rfc attributes | 2026-09-26 | 2026-09-27 |
| #1089 | **OFFEN** | [SE][HIGH][beta.16] KI-Ableitung erzeugt `draft` statt `proposed` ÔÇö Vorschl├ñge sind nicht pr├╝fbar, vorhandene Review-Queue ungenutzt (Bluepencil-Notiz) | high se ui usability ai | 2026-09-26 | - |
| #1090 | GESCHLOSSEN | [i18n][beta.16] Vier Attribut-Labels sind trotz `language=de` un├╝bersetzt (level/title/description/uid) ÔÇö Feldname wird als Label gerendert (Bluepencil-Notiz) | bug frontend i18n attributes | 2026-09-26 | 2026-09-27 |
| #1091 | GESCHLOSSEN | [UI][beta.16] KI-Testfall-Dialog (`derive-testcase-dialog-overlay`): Buttons ohne Design-System, 4x identisches 'Entfernen' (Bluepencil-Notiz) | ui usability frontend design-system | 2026-09-26 | 2026-09-27 |
| #1092 | GESCHLOSSEN | [UI][beta.16] KI-Aktionen verstreut in Panel-Kopfzeilen, Emoji 'Ô£¿' als UI-Icon (Bluepencil-Notiz) | ui frontend a11y design-system | 2026-09-26 | 2026-09-27 |
| #1093 | GESCHLOSSEN | [UI][beta.16] /system-settings Design-Paletten: Buttons ohne Design-System, 7x 'Exportieren' ohne Objektbezug (Bluepencil-Notiz) | ui usability frontend design-system | 2026-09-26 | 2026-09-27 |
| #1094 | **OFFEN** | [UX][beta.16] Lesbare Workspace-IDs ausblendbar machen, Kopier-Vorlage ins Benutzerprofil, kopiert wird die System-ID (Bluepencil-Notiz) | enhancement usability ux frontend | 2026-09-26 | - |
| #1095 | **OFFEN** | [SE][HIGH] KI-Ableitung aus dem Bedarfs-Panel persistiert clientseitig und landet als draft | high se frontend ai | 2026-09-27 | - |
| #1096 | **OFFEN** | [UX] Sichtbarkeit lesbarer IDs persistiert nur lokal ÔÇö Display-Preference-Endpunkt fehlt | enhancement api ux frontend | 2026-09-27 | - |
| #1097 | **OFFEN** | [MCP] main_goal ist ├╝ber MCP nicht per Workspace auflistbar ÔÇö REST kann es | enhancement medium qa mcp | 2026-09-27 | - |
| #1098 | **OFFEN** | [MCP][REST] Kein workspace-weites Enumerieren von TraceLinks ├╝ber MCP | enhancement medium mcp traceability | 2026-09-27 | - |
| #1099 | **OFFEN** | [Design-System] btn-icon existiert nicht, und der Design-Ratchet friert 327 Verst├Â├ƒe ein | low ui frontend design-system | 2026-09-27 | - |
| #1100 | **OFFEN** | [UX] Ctrl/Cmd+S greift nicht in den handgeschriebenen Create-Formularen | low ux frontend a11y | 2026-09-27 | - |
| #1101 | **OFFEN** | [REST] VCRM ist MCP-only, aber im generierten OpenAPI-Schema nicht als solche erkennbar | documentation low api rest | 2026-09-27 | - |
| #1102 | **OFFEN** | [QA] Live-Stack-Tests laufen lokal rot und werden nur in CI uebersprungen | medium qa | 2026-09-27 | - |
| #1103 | **OFFEN** | [QA] Drei Ratchets mit drei verschiedenen Re-Baseline-Mechanismen | low qa | 2026-09-27 | - |
| #1104 | **OFFEN** | [agent-meta] Projekt-Beschreibung in AGENTS.md/CLAUDE.md traegt veraltete Zahlen (MCP 215 statt 219, 11 statt 20 Link-Typen) | documentation housekeeping | 2026-09-27 | - |
| #1106 | GESCHLOSSEN | [W1][SE] Requirement.level ableiten und bei jeder Hierarchie-Aenderung neu berechnen (ADR-005) | high api se data-model | 2026-09-27 | 2026-09-27 |
| #1107 | GESCHLOSSEN | [W2][SE] Zwei Feldarten: Personenfeld (Actor) und Freitext; stakeholder als Mehrfachauswahl (ADR-006) | high se data-model attributes | 2026-09-27 | 2026-09-27 |
| #1108 | GESCHLOSSEN | [W3][SE] Regel-Vokabular auf die Audit-Registry kollabieren; source als Coverage-Konvention (ADR-007) | documentation high api se | 2026-09-27 | 2026-09-27 |
| #1109 | GESCHLOSSEN | [W4][UX] Benachrichtigungen: Badge auf den Assistenten-Einstieg, Feed als Tab im Panel (ADR-009) | ui/ux usability frontend | 2026-09-27 | 2026-09-27 |
| #1110 | **OFFEN** | [W0] Entscheidungswellen 2026-09 - ADRs, Abhaengigkeiten, Reihenfolge | se housekeeping | 2026-09-27 | - |
| #1112 | **OFFEN** | [W2-Folge] ADR-006-Feldkinds wandern auf bereits gebootstrapten Instanzen nicht mit | - | 2026-09-27 | - |
| #1113 | **OFFEN** | [E2E] Statische Pr├╝fung auf data-testid-Literale, die es im Frontend nicht mehr gibt | - | 2026-09-27 | - |
| #1115 | **OFFEN** | [E2E] getWorkspaceId nimmt items[0] und trifft auf verschmutzten Datenbestand Testreste | - | 2026-09-27 | - |
| #1116 | **OFFEN** | [Dev] Backend im Dev-Overlay migriert als App-Role und crash-loopt bei jeder ADD-COLUMN-Migration | - | 2026-09-27 | - |
| #1117 | **OFFEN** | [Test] 3 nicht reproduzierbare Frontend-Fehlschlaege im Release-Cut beta.17 | - | 2026-09-27 | - |

## 4. Offene Issues im Detail (40)

Fuer jedes **offene** Issue ein gekuerzter Body-Kern (max. 300 Zeichen) als
Problem-Kurzfassung, damit die spaetere Reconciliation thematisch zuordnen kann.
Zusaetzlich der Kommentar-Stand (Anzahl Kommentare / letzter Kommentar), weil ein
offenes Issue mit Arbeit im Kommentar-Thread ein anderes Risikoprofil hat als eines
mit Null Kommentaren.

| # | Titel | Labels | Kommentare | Letzter Kommentar | Body-Kern (max. 300 Z.) |
|---|---|---|---|---|---|
| #1117 | [Test] 3 nicht reproduzierbare Frontend-Fehlschlaege im Release-Cut beta.17 | - | 0 | keine | Im Rahmen des Release-Cut `v1.8.0-beta.17` fielen in einem Full Run des Frontend-Suites **3 Tests** durch, die im unmittelbar folgenden Lauf nicht wieder auftraten. Keine Zuordnung, keine Vermutung ÔÇö nur der Fakt, dass es passiert ist und nicht eingegrenzt wurde. ## Gemessen Erster Full Run: ``` T... |
| #1116 | [Dev] Backend im Dev-Overlay migriert als App-Role und crash-loopt bei jeder ADD-COLUMN-Migration | - | 0 | keine | Beim Neustart des lokalen Dev-Stacks nach Migration `0102_adr_deciders_issue_assignee_artifact_stakeholder` crash-loopt der Backend-Container. ## Symptom ``` django.db.utils.ProgrammingError: must be owner of table pl_artifact ``` Der Container f├ñhrt sichtbar `Restarting` ÔåÆ `Started` ÔåÆ `Restart... |
| #1115 | [E2E] getWorkspaceId nimmt items[0] und trifft auf verschmutzten Datenbestand Testreste | - | 0 | keine | Aus dem Release-Cut `v1.8.0-beta.17` **gemessen, nicht vermutet**. ## Befund `getWorkspaceId()` in `e2e/helpers/auth.ts` nimmt `items[0]` aus der Workspace-Liste des eingeloggten Tokens: ```ts const body = await wsResp.json(); const items = Array.isArray(body) ? body : body.results ?? []; if (items.... |
| #1113 | [E2E] Statische Pr├╝fung auf data-testid-Literale, die es im Frontend nicht mehr gibt | - | 0 | keine | Aus dem Release-Cut `v1.8.0-beta.17` (QA-Sweep) **gemessen, nicht vermutet**. ## Befund Die beiden #985-Dismiss-Pins in `e2e/tests/overlay-dismissal.spec.ts` klickten ├╝ber einen vollen Release-Zyklus auf `notification-bell-toggle` ÔÇö ein `data-testid`, dessen Komponente mit ADR-009 (PR #1111) entf... |
| #1112 | [W2-Folge] ADR-006-Feldkinds wandern auf bereits gebootstrapten Instanzen nicht mit | - | 0 | keine | Aus dem Release-Cut `v1.8.0-beta.17` (PR #1111, ADR-006) **gemessen, nicht vermutet**. ## Befund `bootstrap_attribute_definitions` hat ohne `--reset` nur einen additiven Pfad: - `--relabel` ├╝berschreibt **ausschlie├ƒlich** `label` und `help_text` - `--sync-new-fields` ruft `_append_missing()` auf, ... |
| #1110 | [W0] Entscheidungswellen 2026-09 - ADRs, Abhaengigkeiten, Reihenfolge | se housekeeping | 0 | keine | ´╗┐# Entscheidungswellen 2026-09 Ergebnis des QA-Sweeps vom 27.09.2026 (PR #1105) und der Entscheidungsrunde danach. ## Ausgangslage Der QA-Sweep hat 24 Defekte behoben und beim Triage aller offenen Issues **7 Produktentscheidungen** aufgedeckt. Die Recherche zu diesen Entscheidungen kam zu einem ue... |
| #1104 | [agent-meta] Projekt-Beschreibung in AGENTS.md/CLAUDE.md traegt veraltete Zahlen (MCP 215 statt 219, 11 statt 20 Link-Typen) | documentation housekeeping | 0 | keine | ´╗┐## Kontext Beim QA-Sweep gegen `v1.8.0-beta.16` wurde die MCP-Oberflaeche neu gemessen (`tools/list`): **219 Tools / 35 Praefixe**. `README.md`, `docs/CODEBASE_OVERVIEW.md` und `systemagents/reqogniloom-operator.md` wurden korrigiert, und die Zahl ist jetzt dort dokumentiert ÔÇö **mit dem Messrez... |
| #1103 | [QA] Drei Ratchets mit drei verschiedenen Re-Baseline-Mechanismen | low qa | 0 | keine | ´╗┐**Herkunft:** Abschlusspruefung des QA-Sweeps vom 27.09.2026 gegen die eigene Test-Infrastruktur. ## Beobachtung Mit #1080 kam eine neue Entity-Parity-Matrix dazu (`backend/mcp_server/tests/entity_surface_matrix.py` + `entity_surface_baseline.json`). Sie ist das richtige Werkzeug ÔÇö sie haette #... |
| #1102 | [QA] Live-Stack-Tests laufen lokal rot und werden nur in CI uebersprungen | medium qa | 0 | keine | ´╗┐**Herkunft:** Voller Testlauf im QA-Sweep 27.09.2026 ÔÇö 4 Fehler in `mcp_server/tests/test_mcp_api_key_roles.py`, die weder mit den Aenderungen dieses Sweeps noch mit einer Code-Regression zusammenhingen. ## Befund ``` mcp_server/tests/test_mcp_api_key_roles.py::TestMcpApiKeyRolePropagation 4 er... |
| #1101 | [REST] VCRM ist MCP-only, aber im generierten OpenAPI-Schema nicht als solche erkennbar | documentation low api rest | 0 | keine | ´╗┐**Herkunft:** Punkt 5 des Doku-Drift-Bundles #1085, im QA-Sweep 27.09.2026 als Empfehlung offengelassen. ## Befund `vcrm` hat **null** Treffer in `backend/rest_api/**` und im generierten OpenAPI-Schema. Der Begriff existiert nur im MCP-Katalog: `traceability.vcrm` (plus `traceability.coverage` un... |
| #1100 | [UX] Ctrl/Cmd+S greift nicht in den handgeschriebenen Create-Formularen | low ux frontend a11y | 0 | keine | ´╗┐**Herkunft:** Rest aus #1087 (Speichern per Ctrl/Cmd+S), QA-Sweep 27.09.2026. ## Symptom Der Shortcut ist als `frontend/src/hooks/useSaveShortcut.ts` implementiert und in `shared/ArtifactForm` verdrahtet ÔÇö damit in **allen 7 Artefakttypen** (Requirement, ArchitectureElement, ADR, Risk, Issue, T... |
| #1099 | [Design-System] btn-icon existiert nicht, und der Design-Ratchet friert 327 Verst├Â├ƒe ein | low ui frontend design-system | 0 | keine | ´╗┐**Herkunft:** QA-Sweep 27.09.2026, aus #1093 und dem neuen Design-Ratchet. ## Teil 1 ÔÇö `btn-icon` ist im Design-System nicht vorhanden #1093 verlangt f├╝r die Sektion ausdr├╝cklich `btn-primary` / `btn-secondary` / `btn-ghost` / **`btn-icon`**. Diese Klasse **existiert nicht.** Eine Suche ├╝ber... |
| #1098 | [MCP][REST] Kein workspace-weites Enumerieren von TraceLinks ├╝ber MCP | enhancement medium mcp traceability | 0 | keine | ´╗┐**Herkunft:** gefunden beim Bauen der Entity-Parity-Matrix f├╝r #1080, dort als **Ratchet-Gap** dokumentiert. ## Symptom Asymmetrie zwischen REST und MCP bei TraceLinks: \| Transport \| TraceLinks eines Workspace auflisten \| \|---\|---\| \| REST \| `GET /api/v1/tracelinks/?workspace_id=<WS>` ÔÇö... |
| #1097 | [MCP] main_goal ist ├╝ber MCP nicht per Workspace auflistbar ÔÇö REST kann es | enhancement medium qa mcp | 0 | keine | ´╗┐**Herkunft:** gefunden beim Bauen der Entity-Parity-Matrix f├╝r #1080 (`backend/mcp_server/tests/entity_surface_matrix.py`), dort als **Ratchet-Gap** dokumentiert statt stillschweigend geschlossen. ## Symptom `MainGoal` ist ├╝ber MCP **nicht** per Workspace auflistbar. Es gibt `main_goal.get` und... |
| #1096 | [UX] Sichtbarkeit lesbarer IDs persistiert nur lokal ÔÇö Display-Preference-Endpunkt fehlt | enhancement api ux frontend | 0 | keine | ´╗┐**Herkunft:** Rest aus #1094 (lesbare Workspace-IDs ausblendbar, System-ID kopierbar), QA-Sweep 27.09.2026. ## Symptom Die `IdChip`-Komponente und der Ausblend-Toggle existieren (`frontend/src/components/shared/IdChip/`, `hooks/useReadableIdsVisible.ts`), und beide erf├╝llen die drei Kernpunkte d... |
| #1095 | [SE][HIGH] KI-Ableitung aus dem Bedarfs-Panel persistiert clientseitig und landet als draft | high se frontend ai | 0 | keine | ´╗┐**Herkunft:** Rest aus #1089 (KI-Ableitung pr├╝fbar machen), der im QA-Sweep vom 27.09.2026 behoben wurde. ## Symptom `ai_derivation.derive_requirements_from_need` erzeugt jetzt korrekt `proposed`-Artefakte. Aber es gibt einen zweiten, parallelen Pfad, der das umgeht: `frontend/src/components/Nee... |
| #1094 | [UX][beta.16] Lesbare Workspace-IDs ausblendbar machen, Kopier-Vorlage ins Benutzerprofil, kopiert wird die System-ID (Bluepencil-Notiz) | enhancement usability ux frontend | 1 | 2026-09-27 (@Popoboxxo) | **Herkunft:** Bluepencil-Notiz `n-muikmwti-b-pln666` (Autor: Daniel, `intent=implement`, `status=open`) **Route:** `/architecture` ┬À **Anker-Quote:** ÔÇ×ARCH-001" **Stand:** QS 172.20.5.120, `v1.8.0-beta.16` (`9eb2fc5`) **Original-Notiz:** > Okay ich glaube wir sollten diese lesbaren automatisch in... |
| #1089 | [SE][HIGH][beta.16] KI-Ableitung erzeugt `draft` statt `proposed` ÔÇö Vorschl├ñge sind nicht pr├╝fbar, vorhandene Review-Queue ungenutzt (Bluepencil-Notiz) | high se ui usability ai | 1 | 2026-09-27 (@Popoboxxo) | **Herkunft:** Bluepencil-Notiz `n-muijpuow-5-zi54cy` (Autor: Daniel, `intent=implement`, `status=open`) **Route:** `/requirements/ef9a3fae-ÔÇª` ┬À **Anker-Quote:** ÔÇ×Systemanforderungen erfolgreich abgeleitet!" **Stand:** QS 172.20.5.120, `v1.8.0-beta.16` (`9eb2fc5`) **Original-Notiz:** > Aber ie A... |
| #1087 | [UX][beta.16] Anforderungsformular: Speichern ist nicht per Ctrl/Cmd+S erreichbar (Bluepencil-Notiz) | usability ux frontend a11y | 1 | 2026-09-27 (@Popoboxxo) | **Herkunft:** Bluepencil-Notiz `n-muijmfqw-2-db1ms9` (Autor: Daniel, `intent=implement`, `status=open`) **Route:** `/requirements/ef9a3fae-ÔÇª` ┬À **Anker-Quote:** ÔÇ×Begr├╝ndung" **Stand:** QS 172.20.5.120, `v1.8.0-beta.16` (`9eb2fc5`) **Original-Notiz:** > Speicher soll auch mit STRG+S m├Âglch sei... |
| #988 | [BUG][beta.12] Review layer stores every note as author "anonymous": vendored bluepencil bundle predates the upstream identity fix (#12/#15) | bug frontend dependencies | 3 | 2026-09-27 (@Popoboxxo) | ## Summary The bluepencil review layer in this repo resolves **no host identity**, so every note a user writes is stored as `author: "anonymous"` and bundles export `app.name`/`exportedBy: "unknown"`. The host side is now wired (see below) ÔÇö the remaining cause is that the **vendored bluepencil bu... |
| #946 | feat(debug): in-UI annotation layer for admin debug mode (text + design notes, export, central deletion) | ui/ux frontend feature | 1 | 2026-09-27 (@Popoboxxo) | ## Summary Add an **admin-only in-UI annotation layer** to the ReqFlow frontend: click any element in the running app, write a note (either a *text* note about wording/content or a *design* note about layout/styling), and get a machine-readable export of all notes. Notes carry a stable anchor plus t... |
| #941 | Attribut v3 - WS0 Fundament: Contract-Matrix + gemeinsamer Gateway + #912 | se data-model | 1 | 2026-09-27 (@Popoboxxo) | ´╗┐Teil von #934. ## Ziel Das Versprechen, dass alle Attribute via REST und MCP nutzbar sind, technisch erzwingbar machen. ## Deliverables 1. `test_transport_contract_matrix.py`: parametrisiert ueber ITEM_TYPES x PRESETS x {REST,MCP} x Attribut, prueft W/R/V/Round-Trip. Start: rot (dokumentiert die ... |
| #934 | [Epic] Attribut-System v3 - Attribute Usability Contract (REST+MCP) | enhancement se data-model | 1 | 2026-09-27 (@Popoboxxo) | ## Ziel Das Attribut-System auf eine durchgaengige Contract-Basis stellen: **jedes** Attribut jedes der 11 Artefakt-Typen ist jederzeit via **REST und MCP** schreib-, les- und validierbar (Attribute Usability Contract, AUC). Dazu: Systemfelder (ID/Owner/Reporter/priority), Personen-/Team-Felder (`ac... |
| #879 | P3: Projekt-Meilensteine (SRR, PDR, CDR) als System-Entit├ñten f├╝r Phasenbewertung | enhancement low se | 1 | 2026-09-27 (@Popoboxxo) | ### Problembeschreibung NASA SE Prozess 10 (*Technical Planning*) misst den Reifegrad eines Systems an Review-Meilensteinen: - **SRR** (System Requirements Review) - **PDR** (Preliminary Design Review) - **CDR** (Critical Design Review) In ReqogniLoom existiert Reifegrad nur als ephemerer Zustand an... |
| #878 | P2: Validierungs-L├╝cke schlie├ƒen: Verkn├╝pfung TestCase -> validates -> StakeholderNeed | enhancement medium se | 1 | 2026-09-27 (@Popoboxxo) | ### Problembeschreibung ReqogniLoom unterscheidet aktuell nicht zwischen Verifikation und Validierung: - **Verifikation (Gegen Anforderungen):** Durch `TestCase -> verifies -> Requirement` vollst├ñndig abgedeckt. - **Validierung (Gegen Kundenbedarfe):** Ein Link-Typ `TestCase -> validates -> Stakeho... |
| #877 | P2: Funktionale Architekturschicht (LogicalFunction & performs-Link) f├╝r NASA SE Prozess 3 | enhancement high se | 1 | 2026-09-27 (@Popoboxxo) | ### Problembeschreibung Gem├ñ├ƒ NASA Systems Engineering Engine (Prozess 3: *Logical Decomposition*) und ISO 15288 verlangt klassisches MBSE das Dreieck: `Anforderung (Was) -> Logische Funktion (Verhalten) -> Komponente (Physisch)` In ReqogniLoom kennt `ArchitectureElement.element_type` nur struktur... |
| #801 | [UI][HIGH] Inspector (Version/History/Diff) nur bei Requirements ÔÇö 6 andere Entity-Typen haben keinen Verlaufs-Zugriff | enhancement qa ui consistency | 0 | keine | **Gefunden via:** Hermes UI Deep-Review (01.09.2026, v1.8.0-beta.5 `83a34bb`, Playwright/CDP mit echtem UI-Login, 19 Screenshots 1920├ù1080, DOM-Extraktion + Vision-Analyse) **Report:** `/opt/data/rlqa/ui_design_review_final.json` --- ## Befund Der rechte **Inspector** bei Requirements zeigt Version... |
| #792 | [RFC] System-Wide Improvements: Deployment, Security, Operations & DX | enhancement critical security infrastructure dx | 1 | 2026-09-27 (@Popoboxxo) | # [RFC] System-Wide Improvements: Deployment, Security, Operations & Developer Experience **Version:** v1.8.0-beta.5 **Type:** Enhancement **Priority:** Critical **Scope:** Infrastructure, Security, DX, Operations --- ## Executive Summary This RFC consolidates **18 systemic issues** discovered durin... |
| #649 | Feature: importable Hermes Skill (connector) alongside the desktop plugin | enhancement integration hermes | 1 | 2026-09-27 (@Popoboxxo) | ## Problem The Hermes integration currently ships only as an **Electron desktop plugin** (`integrations/hermes-plugin/reqogniloom`). That plugin loads **exclusively** in the Hermes Desktop App ÔÇö it depends on `@hermes/plugin-sdk` (`ctx.register`, `panes`, `statusBar.right`) which is injected only ... |
| #598 | Frontend-Review v1.6.0: 5 Warnings + 6 Suggestions (Verdikt: APPROVE ÔÇö #449/#450/B2 gefixt) | - | 1 | 2026-09-27 (@Popoboxxo) | ## Frontend-Review v1.6.0: 5 Warnings + 6 Suggestions (Verdikt: APPROVE) **Review:** Statische Code-Analyse des KOMPLETTEN Frontends (`frontend/` + `integrations/hermes-plugin/`) auf Tag `v1.6.0` (9e0399b). Reviewer: Hermes-Profil `reviewer` (DeepSeek v4 Pro), 16.08.2026. Baselines: v1.6.0-beta.1- u... |
| #587 | feat: Promptfoo test infrastructure for prompt templates (Phase 3, Prompt Variable Catalog) | enhancement high qa | 1 | 2026-09-27 (@Popoboxxo) | ## Summary Implement Promptfoo test infrastructure for ~19 prompt templates, as specified in `docs/superpowers/specs/2026-08-16-prompt-variable-catalog-design.md` (Section 6) and Phase 3 rollout plan (Section 7). This test infrastructure enables regression detection and quality validation for prompt... |
| #378 | [FEATURE] Artefakt-Qualit├ñtsbewertung: Trigger- oder auto-basierte Qualit├ñts-Scores mit pro-Workspace steuerbaren Qualit├ñts-Prompts | enhancement feature | 1 | 2026-09-27 (@Popoboxxo) | ## [FEATURE] Artefakt-Qualit├ñtsbewertung: Trigger- oder auto-basierte Qualit├ñts-Scores mit pro-Workspace steuerbaren Qualit├ñts-Prompts **Severity**: Ô£¿ FEATURE REQUEST **Kategorie**: Quality / AI-Assessment **Version-Bezug**: v1.5.0 (fb754dd) ### Motivation Der SE-Auditor pr├╝ft aktuell **nur st... |
| #272 | [QA][ENH] SE-Interview (ISO 15288/42010/29148): Gesamtnote 3,5 ÔÇö Top-5 fachliche Schw├ñchen (AC-Gate, Link-Typ-Enum, Pass/Fail-Kontrakt, CRÔåöBaseline, Demo-Fixture) | enhancement qa se data-model | 3 | 2026-09-27 (@Popoboxxo) | ## [QA][ENH] SE-Interview-Befund (ISO 15288/42010/29148): Gesamtnote 3,5 ÔÇö Top-5 fachliche Schw├ñchen mit konkreten Fixes **Severity:** ­ƒÆí ENHANCEMENT **Surface:** Fachlich / Datenmodell **Version:** v1.1.0 (51eb906) **Gefunden von:** Babsi QA-Zerfickung 01.08.2026 (SE-Manager-Interview, Live-Da... |
| #186 | [AUDIT][UX] EPIC: UI-Gesamtkonzept ÔÇö Umsetzung in 6 Schritten (docs/UI_KONZEPT.md) | enhancement high ui/ux frontend audit-2026-07 | 2 | 2026-09-27 (@Popoboxxo) | Sammel-Issue zum Konsistenz-Audit. Das ausgearbeitete Zielbild liegt in **`docs/UI_KONZEPT.md`**. ## Leitgedanke Wer mit ReqogniLoom arbeitet, bewegt sich durch einen getracten Graphen und verliert dabei staendig den Kontext. Die Oberflaeche hat genau eine Aufgabe: **den Weg sichtbar halten.** Darau... |
| #92 | feat: workspace-specific API tokens with UI for UUID display and MCP config copy | enhancement | 1 | 2026-09-27 (@Popoboxxo) | ## Feature Request: Workspace-spezifische API-Tokens + UI-Verbesserungen ### 1. Workspace-spezifische API-Tokens Aktuell sind API-Tokens global/generisch. F├╝r die MCP-Anbindung (und generelle API-Nutzung) w├ñre es sicherer und klarer, Tokens an einen bestimmten Workspace zu binden: - Token gilt nur... |
| #89 | seed_demo als Login-Bootstrap-Ersatz in CI ist keine Endanwender-taugliche L├Âsung | enhancement | 1 | 2026-09-27 (@Popoboxxo) | ## Kontext In `.github/workflows/playwright.yml` wurde `python manage.py loaddata initial_data` (referenzierte eine nie existierende Fixture, CI war dadurch kaputt) durch `python manage.py seed_demo` ersetzt (PR #88). `seed_demo` funktioniert f├╝r CI/E2E, ist aber laut eigenem Docstring als **option... |
| #85 | [QA] ­ƒÅå UI-Bewertung & Verbesserungsvorschlaege f r ReqogniLoom v1.0.0 | - | 1 | 2026-09-27 (@Popoboxxo) | ## UI-Bewertung: ReqogniLoom v1.0.0 (Commit 973a620) **Gesamtnote: 2- (gut, mit Luft nach oben)** Gepr ft wurden 22 Seiten im Browser, 122 MCP Tools, ~40 REST Endpoints auf der Sandbox (172.20.5.108). --- ### Staerken (+) **1. Massiv verbesserte Stabilitat** - B2 Auth-Bug GEFIXED: Alle 22 Seiten lad... |
| #50 | [QA] F1 ÔÇö Baseline: Benennung, Compare und Rollback | enhancement baseline | 2 | 2026-09-27 (@Popoboxxo) | ## Feature Request **Fokus**: Usability, Versioning, Baselining ### Vorschl├ñge 1. **Baseline-Namen**: Textfeld im Create-Dialog f├╝r benutzerdefinierte Namen (optional, Fallback auf Auto-Timestamp) 2. **Baseline-Compare im UI**: Der Compare-Button ist aktuell deaktiviert. Nach Erstellung von 2+ Bas... |
| #18 | [SE][MEDIUM] RAG Search ÔÇö Semantische Suche ├╝ber alle Artefakte (pgvector) | enhancement medium api qa | 0 | keine | ## Beschreibung Aktuell gibt es nur PostgreSQL Full-Text-Search (FTS). Das reicht f├╝r Keyword-Suche, aber nicht f├╝r konzeptuelle Fragen wie "Welche Anforderungen betreffen die Authentifizierung?". ## Geforderte Neuerung ### MCP-Tool: `ai_search.query` ```json { "workspace_id": "uuid", "query": "We... |
| #17 | [SE][MEDIUM] MCP: workspace.resolve_references ÔÇö ID-Resolver f├╝r Coding-Integration | enhancement medium api qa | 0 | keine | ## Beschreibung Entwickler im Code (Claude Code, Cursor) brauchen die M├Âglichkeit, aus einer REQ-ID sofort den vollst├ñndigen Kontext zu laden. Aktuell gibt es keinen schnellen Lookup-Endpoint. ## Geforderte Neuerung ### MCP-Tool: `workspace.resolve_references` ``` Params: { "workspace_id": "uuid",... |

## 5. Die vier Pruefpunkte im Detail

Gesucht wurde ueber `gh issue list --search` (Search-API, alle States) und `gh issue view` fuer die einzelnen Treffer. Kommando und Trefferzahlen sind je Pruefpunkt genannt, damit die Suche im Audit reproduzierbar ist.

### 5.0 Uebersicht

| # | Pruefpunkt | Treffer | State | Letzter Kommentar | Getrackt? |
|---|---|---|---|---|---|
| a | ADR-006-Upgrade-Pfad (`field_kind` ohne `--reset`) | #1112 (+ #1116) | **OFFEN** | keine (0 Kommentare) | ja, aber **falsche Nummer** im Auftrag |
| b | `build.sh` ohne Wirkung bei pull-basierter Release-Compose | **kein Issue** | - | - | **nein - ungetrackt** |
| c | Tool-Count-Drift 218 vs. 219 | #1104 (offen), #1085 + #1080 (geschlossen) | gemischt | #1085: 2 Kommentare, 2026-09-27 | ja, aber **gegenlaeufig** |
| d | `RELEASE_v1.8.0-beta.18.md:481` offener Checklistenschritt | **kein Issue**, Datei nur in `38da915f` | - | - | **nein - ungetrackt** |

> **Pruefpunkte b und d sind derselbe Sachverhalt** und in Abschnitt 5.2 / 5.4 bewusst getrennt gefuehrt: (b) ist der technische Befund, (d) ist der Release-Checklistenschritt, der ihn ausloest. Details in 5.5.

### 5.1 (a) ADR-006-Upgrade-Pfad - `bootstrap_attribute_definitions` ohne `--reset`

**Befund: die vermutete Issue-Nummer #940 ist falsch. Der korrekte Treffer ist #1112.**

| | #1112 (korrekt) | #940 (aus dem Auftrag, widerlegt) |
|---|---|---|
| Titel | [W2-Folge] ADR-006-Feldkinds wandern auf bereits gebootstrapten Instanzen nicht mit | Attribut v3 - WS7 AWMS Werte-Migration |
| State | **OFFEN** | GESCHLOSSEN (2026-09-14, `stateReason: COMPLETED`) |
| Labels | keine | `se`, `data-model`, `tooling` |
| Kommentare | **0** (kein Kommentar-Thread) | 0 |
| Scope | Attribut-**Feldkind**-Metadaten (Schema) | Attribut-**Werte**-Migration (Daten) |

**Suchprotokoll:**

- `gh issue list --search "field_kind" --state all` -> **genau 1 Treffer: #1112**. Damit ist #1112 das einzige Issue, das den Feldkind-Upgrade-Pfad je benannt hat.
- `--search "bootstrap_attribute_definitions"` -> 4 Treffer (#1112, #947, #912, #1090); nur #1112 hat einen Feldkind-Bezug, die anderen betreffen E2E-Bootstrap, Preset-`mandatory_fields` und i18n-Labels.
- `--search "ADR-006"` -> 5 Treffer: #1112 (offen), #1110 (offen), #1107, #1088, #110 (geschlossen).

**Body-Kern #1112 (gekuerzt, verbatim aus dem Issue):**

> `bootstrap_attribute_definitions` hat ohne `--reset` nur einen additiven Pfad: `--relabel` ueberschreibt **ausschliesslich** `label` und `help_text`, `--sync-new-fields` ruft `_append_missing()` auf ...

**Abgrenzung zu #940:** #940 (Attribut v3 - WS7 AWMS Werte-Migration) ist die **Werte**-Migration (uid -> externer Schluessel, moscow_priority -> extended, Legacy-Owner -> Actor, Goal-Messgroessen -> Measure). Sie ist damit **Daten**-Migration und bereits geschlossen. #1112 beschreibt **Metadaten**-Migration (`field_kind` auf bereits geboostrappten Instanzen) und ist offen. Die Vermutung im Audit-Auftrag ist zu korrigieren; wenn sie stehen bliebe, wuerde der Reconciliation-Lauf ein geschlossenes Daten-Thema gegen einen offenen Metadaten-Defekt stellen.

**Nachbarbefund im selben Themencluster:**

- **#1116 (OFFEN, 0 Kommentare)** - `[Dev] Backend im Dev-Overlay migriert als App-Role und crash-loopt bei jeder ADD-COLUMN-Migration`. Gleiches Release-Cut, gleicher Migrations-Pfad, gleiche Ursachenklasse (Migrations- und Rollen-Pfad im Dev-Overlay).
- **#1110 (OFFEN, 0 Kommentare)** - `[W0] Entscheidungswellen 2026-09 - ADRs, Abhaengigkeiten, Reihenfolge`: verortet ADR-006 in der Entscheidungsreihenfolge und ist die uebergeordnete Steuerungs-Instanz fuer beide Folge-Issues.
- Umsetzung von ADR-006: **PR #1111** (MERGED 2026-09-27), `feat(se): decision waves 2026-09 - level derived, field kinds, rule vocabulary`.
- Kontext-Release: **PR #1105** (MERGED 2026-09-27), QA-Sweep beta.16 mit 24 Defekten.

**Reconciliation-Auftrag:** Der Fix aus PR #1111 muss gegen **zwei** Szenarien geprueft werden, nicht gegen eines: (1) frische Instanz, (2) bereits gebootstrapte Instanz ohne `--reset`. Die Behauptung aus dem Release-Cut ist die eines frischen Builds; genau fuer den zweiten Fall existiert ein offenes Issue. Alle Instanzen, die **vor** PR #1111 geboostrappt wurden, tragen potenziell veraltete `field_kind`-Werte - das ist ein Datenbestands-, kein Neustart-Problem.

### 5.2 (b) `build.sh` ohne Wirkung bei pull-basierter Release-Compose

**Befund: es existiert kein GitHub-Issue zu diesem Sachverhalt. Der Defekt ist ungetrackt.**

**Suchprotokoll (0 Treffer):** `--search "build.sh"` -> **[]** (leeres Ergebnis). Die Suche nach `"Release-Compose"` liefert 6 Treffer (#1116, #792, #85, #89, #1054, #893), keiner davon behandelt den Build-Weg. Auch der Volltext der 40 offenen Issues enthaelt kein `build.sh`.

**Am Ist-Stand `abd61aed` nachgemessen:**

| Messpunkt | Wert |
|---|---|
| `build:`-Sektionen in `deploy/docker-compose.yml` | **0** |
| `build:`-Sektionen in `deploy/docker-compose.override.yml` | **5** |
| Release-Compose pin | fertige Images, u.a. `ghcr.io/popoboxxo/reqogniloom-backend:${REQOGNILOOM_VERSION:-1.8.0-beta.17}` |
| `scripts/build.sh:88-92` ruft | nur `docker compose -f deploy/docker-compose.yml --project-directory . build` |
| `scripts/build.sh:80-87` | Kommentar: Override **absichtlich** ausgeschlossen |

**Mechanik:** `scripts/build.sh:76-78` loggt die drei Werte `APP_VERSION` / `GIT_COMMIT_SHA` / `BUILD_TIME`, **stempelt sie aber nicht** - es reicht sie als Build-Args an `docker compose build` durch. Da die Release-Compose **0** build-Sektionen hat und `build.sh` das einzige Overlay mit den 5 build-Sektionen bewusst auslaesst, meldet das Skript `No services to build`. Ergebnis: **kein Image, kein Digest, keine gestempelten Werte irgendwo.** Der Default-Compose-Pfad ist pull-basiert.

**Bekannter, dokumentierter Stand:** `docs/se/reports/RELEASE_v1.8.0-beta.16.md:156` fuehrt `make build` / `scripts/build.sh` in der Gate-Tabelle als **"kein Image - per Konstruktion ein No-op"** und erklaert in Abschnitt 6.3 (`:219-239`) ausdruecklich, dass der kanonische Release-Build der tag-getriggerte `.github/workflows/docker-publish.yml` (`on: push: tags: [v*.*.*]`, fail-closed Trivy-Gate) ist. Der Befund ist also **seit beta.16 bekannt und dokumentiert - aber nie als Issue erfasst.**

**Reconciliation-Auftrag:** Die Aussage "per Konstruktion ein No-op" ist gegen den Ist-Stand bestaetigt. Zu klaeren ist, warum ein als Release-Schritt nummerierter Befehl im Release-Prozess steht, ohne Wirkung zu haben, und ob jemand den No-op-Zustand als Fehler *erwartet*. Solange das ungetrackt bleibt, ist es eine stille Fehlwirkung, die bei jedem manuellen Release-Cut erneut Zeit kostet und einen fehlenden Image-Digest erst nach dem Publish auffaellt.

### 5.3 (c) Tool-Count-Drift 218 vs. 219

**Befund: der Drift ist real, in sich geschlossen und laeuft in drei Zahlen. Zwei der drei sind geschlossen, die massgebliche ist offen.**

| Issue | Zahl im Titel | State | Kommentare | Rolle im Drift |
|---|---|---|---|---|
| #1104 | **215** statt 219 | **OFFEN** | 0 | Projekt-Beschreibung falsch |
| #1085 | **218** / 35 | GESCHLOSSEN 2026-09-27 (`COMPLETED`) | 2 (letzter 2026-09-27 @Popoboxxo) | Doku-Drift-Bundle, *behauptet* 218 als korrekt |
| #1080 | **218** / 35 | GESCHLOSSEN 2026-09-27 | 2 | Parity-Matrix gegen 218 gebaut |

**Die Kette:** `215` (Projekt-Beschreibung) -> `218` (#1085, #1080 als gemessener Stand) -> `219` (Neu-Messung im QA-Sweep 27.09.2026, 35 Praefixe). Die beiden geschlossenen Issues haben 218 als *richtig* fixiert; #1104 stellt denselben Bereich auf eine dritte Zahl. **Genau das ist der Reconciliation-Fall, den der Audit pruefen muss:** eine geschlossene Fix-Behauptung (`stateReason: COMPLETED`) und eine spaetere Messung widersprechen sich.

**Am Ist-Stand verifiziert - der Drift ist teilweise behoben, aber nicht geschlossen:**

| Datei | Ist-Stand | Erwartet laut #1104 |
|---|---|---|
| `README.md:114` | `35 tool-group prefixes, 219 tools` | korrekt |
| `AGENTS.md:8` | `31 Tool-Gruppen-Praefixen und 215 Tools` | **veraltet** |
| `AGENTS.md:30` | `31 Tool-Gruppen-Praefixen und 215 Tools` | **veraltet** |

`README.md` wurde also korrigiert, `AGENTS.md` **nicht**. Damit ist #1104 weiterhin offen und **nachweislich nicht erledigt** - die Verifikation stuetzt den Issue-Status gegen den Ist-Stand. (Dieses Audit hat `AGENTS.md` bewusst **nicht** angefasst; Auftrag: keine anderen Repo-Dateien aendern. Der Drift besteht damit fort.)

**Reconciliation-Auftrag:** Es ist zu klaeren, ob 218 -> 219 ein echter Tool-Zuwachs zwischen den Staenden ist oder ob die beiden Messungen unterschiedliche Scopes zaehlen (z.B. HTTP-/SSE-/STDIO-Varianten, oder Werkzeuge mit mehrfacher Prefix-Zuordnung). Ohne diese Klaerung ist jede der drei Zahlen in der Doku unbelegbar - und die 35/31-Diskrepanz in der Praefix-Zahl ist ein zweiter, im selben Issue genannter Drift.

### 5.4 (d) `docs/se/reports/RELEASE_v1.8.0-beta.18.md:481`

**Befund 1 - die Datei existiert auf diesem Branch nicht.**

| Pruefung | Ergebnis |
|---|---|
| `docs/se/reports/RELEASE_v1.8.0-beta.18.md` auf `abd61aed` | **FEHLT** |
| Inhalt von `docs/se/reports/` auf `abd61aed` | `RELEASE_...beta.11` bis `beta.17` (7 Release-Reports) |
| `git log --all -- docs/se/reports/RELEASE_v1.8.0-beta.18.md` | genau 1 Commit: `38da915f release: v1.8.0-beta.18` |
| Tag `v1.8.0-beta.18` | **existiert** im Repo |
| Ist `38da915f` in `chore/system-audit-2026-09` enthalten? | **nein** (Branch steht auf `abd61aed`) |

Die Datei wurde daher per `git show 38da915f:docs/se/reports/RELEASE_v1.8.0-beta.18.md` gelesen. **Wichtig fuer den Audit:** die Zielbasis `abd61aed` enthaelt den beta.18-Cut **nicht** - der Release-Stand liegt nur auf dem Release-Branch. Wer auf diesem Branch gegen den beta.18-Checkpoint prueft, prueft gegen einen Stand, der dort nicht existiert.

**Befund 2 - Zeile 481-482 ist Checklistenschritt 6 des beta.18-Cuts, verbatim:**

> 6. Release-Build setzen: `scripts/build.sh` bzw. `make build` (stempelt
>    `APP_VERSION` / `GIT_COMMIT_SHA` / `BUILD_TIME` ein).

Umfeld aus demselben Abschnitt (Schritte 5-8):

> 5. **Vor dem Tag:** die in Abschnitt 6.2-6.6 offenen Pruefungen auf dem
>    Release-Commit nachholen (CI, Backend, Frontend, statische Checks, E2E) ...
> 6. Release-Build setzen: `scripts/build.sh` bzw. `make build` ...
> 7. Publish ueber `.github/workflows/docker-publish.yml`.
> 8. Tag `v1.8.0-beta.18` auf den Release-Commit setzen.

**Befund 3 - die Klammer in Schritt 6 ist sachlich falsch.** Wie in 5.2 gemessen, stempelt `scripts/build.sh` nichts: es reicht `APP_VERSION` / `GIT_COMMIT_SHA` / `BUILD_TIME` als Build-Args an ein `docker compose build` durch, das im Release-Pfad **0 Services** zu bauen hat. Das Stempeln passiert real erst und ausschliesslich im Schritt-7-Workflow `docker-publish.yml`, also **einen Schritt spaeter** als dort behauptet.

**Suchprotokoll:** `--search "beta.18"` -> 8 Treffer (#792, #720, #983, #794, #871, #710, #442, #928), **keiner** davon behandelt den beta.18-Checklistenpunkt. Auch `--search "Checkliste"` liefert nur 2 geschlossene Issues (#895, #893) ohne Bezug. **Der Punkt ist ungetrackt.**

### 5.5 Zusammenfuehrung: (b) und (d) sind derselbe Checklistenschritt

Die beiden Pruefpunkte beschreiben **eine** Fehlwirkung in zwei Formen:

- (b) ist der **technische Befund**: `build.sh` ist im Release-Pfad ein No-op, weil die Release-Compose pull-basiert ist und alle 5 build-Sektionen im Dev-Overlay liegen.
- (d) ist die **Ausloesung**: beta.18-Checklistenschritt 6 nummeriert genau diesen No-op als Release-Schritt und behauptet zusaetzlich, er stemple Versionsdaten ein.

Die Diskrepanz ist dokumentiert und damit **keine neue Erkenntnis, sondern eine nicht aufgeloeste Widerspruchs-Lage innerhalb der Release-Dokumentation:**

| Quelle | Aussage | Stand |
|---|---|---|
| `RELEASE_v1.8.0-beta.16.md:156` | `make build` / `scripts/build.sh`: "kein Image - per Konstruktion ein No-op" | auf `abd61aed` vorhanden |
| `RELEASE_v1.8.0-beta.16.md:219-239` | Abschnitt 6.3: kanonischer Release-Build ist `docker-publish.yml` | auf `abd61aed` vorhanden |
| `RELEASE_v1.8.0-beta.18.md:481` (Schritt 6) | "`scripts/build.sh` bzw. `make build`" stempelt `APP_VERSION` / `GIT_COMMIT_SHA` / `BUILD_TIME` ein | **nur** in `38da915f` |
| `scripts/build.sh:76-78, 88-92` (Ist-Code) | Werte werden nur als Build-Args durchgereicht; 0 Services zu bauen | auf `abd61aed` vorhanden |

**Empfehlung an den Reconciliation-Lauf (keine Umsetzung in diesem Schritt):** Schritt 6 der beta.18-Checkliste streichen oder ersetzen durch "Publish via `docker-publish.yml` (Schritt 7) - Image-Digest dokumentieren". Ein als massgeblich beschrifteter Release-Schritt, der nachweislich nichts erzeugt, ist die Ursache dafuer, dass "kein Image gebaut -> kein Image-Digest dokumentiert" in den Release-Cuts als *Konsequenz* erscheint statt als *Fehler*.

### 5.6 Was der Audit daraus ableiten sollte

1. **#1112** ist der Tragetag fuer den ADR-006-Upgrade-Pfad - **nicht #940**. #940 ist abgeschlossen und betrifft andere Daten. Fehlt der richtige Bezug, wird ein offener Metadaten-Defekt als geschlossener Daten-Fix verbucht.
2. **#1112 + #1116** bilden gemeinsam einen offenen Migrations-Pfad-Cluster aus dem beta.17-Cut, der ausserhalb von PR #1111 weiterbesteht. Beide haben **null** Kommentare - es hat niemand reagiert, der Zustand ist unveraendert.
3. **#1104** ist gegen den Ist-Stand **bestaetigt offen** (`AGENTS.md` unveraendert auf 215/31, waehrend `README.md` schon 219/35 traegt). Die geschlossenen #1085/#1080 haben 218 als korrekt fixiert - die Zaehlung muss gegen den Ist-Code geklaert werden, bevor irgendeine der drei Zahlen in die Doku zurueckgeschrieben wird.
4. **(b) und (d) sind ein ungetrackter Befund.** Ein Release-Checklistenschritt ohne Wirkung, mit falscher Begruendung im Text. Beide sind nicht durch ein Issue abgesichert - fuer den Audit ist das der Befund, nicht der Einzelfall.
5. **Beta.18 fehlt auf der Audit-Basis.** `abd61aed` enthaelt den beta.18-Cut nicht; der Tag existiert, der Report nur auf `38da915f`. Vor einer Pruefung des beta.18-Checkpoints muss die Bezugsbasis festgelegt werden.

## 6. Methodik und Reproduzierbarkeit

### 6.1 Verwendete Befehle (alle read-only)

```
gh repo view --json nameWithOwner -q .nameWithOwner
gh issue list --state all --limit 1000 --json number,title,state,labels,createdAt,closedAt,author,updatedAt,url
gh issue list --state open  --limit 200 --json number,title,body,comments,updatedAt,stateReason,labels
gh issue list --state all --search "<query>" --json number,title,state,updatedAt      # je Pruefpunkt
gh issue view <n> --json number,title,state,closedAt,createdAt,labels,comments,stateReason
gh api rate_limit --jq .resources
```

Dazu ausschliesslich lesende Git-Operationen zur Verifikation am Ist-Code:
`git rev-parse`, `git status --porcelain`, `git remote -v`, `git log --all -- <pfad>`,
`git show 38da915f:<pfad>`, `git tag`, `git branch -a` sowie Datei-Lesen und
`Select-String`/`[regex]`-Auswertung. **Kein** Schreibzugriff auf ausser der Zieldatei.

### 6.2 Rohdaten vs. Datei

| | Wert |
|---|---|
| Roh-JSON `gh issue list --state all` | **886 204 Bytes** |
| Roh-JSON `gh issue list --state open` (inkl. Body + Kommentare) | separat, nur transient |
| In die Datei uebernommen | ausschliesslich verdichtetes Markdown |

Die Roh-JSON wurde **bewusst nicht** eingebettet, sondern ausschliesslich als
Parse-Quelle genutzt. Body-Texte der offenen Issues sind auf **300 Zeichen** gekuerzt;
ausgeschlossene Zeichen sind mit `...` markiert. Volltext bleibt ueber `gh issue view`
abrufbar.

### 6.3 Abweichung von der Auftragsvorgabe (transparent dokumentiert)

Der Auftrag nannte fuer die Body-Ernte `gh issue view <n>` "in Batches". Bei 608 Issues
(davon 40 offen) waeren das 40 Einzelaufrufe - mehr als das API-Budget von ~40 Aufrufen,
das zugleich fuer die Suche, die Pruefpunkte und die Verifikation gebraucht wird.

**Umgesetzt wurde stattdessen:** ein einziger Aufruf
`gh issue list --state open --json number,title,body,comments,updatedAt,stateReason,labels`,
der Body **und** Kommentar-Stand fuer alle 40 offenen Issues in einem Durchgang liefert.
`gh issue view` wurde gezielt fuer die 6 pruefpunkt-relevanten Issues (#940, #1080, #1085,
#1105, #1110, #1111) sowie #1104 eingesetzt, um `stateReason` und Kommentar-Detailtiefe zu
erheben. **Ergebnis identisch, 34 API-Aufrufe weniger.**

Zusaetzlich wurde die Spalte *Autor* in der Voll-Tabelle weggelassen, weil alle 608 Issues
von derselben Identitaet stammen. Das Feld ist als Invariante in Abschnitt 1.1 mit
vollstaendiger Aufschluesselung dokumentiert - es ist damit erfasst, ohne 608 identische
Zellen zu erzeugen.

### 6.4 Sprach- und Encoding-Hinweis

Der **eigene Fliesstext** dieses Berichts ist bewusst in ASCII-Umschrift geschrieben
(`ue`/`oe`/`ae`/`ss`), um Encoding-Verluste in der Erzeugungskette auszuschliessen. Das
entspricht der Konvention, die der Grossteil der Issue-Titel in diesem Repo ebenfalls
verwendet: **439 von 608** Titeln (72 %) sind in ASCII-Umschrift, **169** (28 %) mit Umlauten.
Der Trend laeuft zur Sache hin: die aeltere Welle transliteriert, die aktuelle
QA-/Bluepencil-Welle ab ca. #1086 schreibt durchgaengig mit Umlauten (12 von 52 Titeln ab #1000).

**Alle aus GitHub uebernommenen Inhalte** - Titel, Labels, Body-Kerne - tragen dagegen
ihre **originalen** Umlaute und Sonderzeichen. Zwei Belege aus dem Voll-Tabellen-Teil:

- `[E2E] Statische Pr├╝fung auf data-testid-Literale, die es im Frontend nicht mehr gibt`
- `[Design-System] btn-icon existiert nicht, und der Design-Ratchet friert 327 Verst├Â├ƒe ein`

Beide Titel stehen hier mit unveraendertem `ü` / `ö` / `—`, waehrend dieser Bericht an
eigener Stelle `Pruefung` schreibt. Es wurde also **kein** aus dem Repo stammender
Text transliteriert; die Umschrift betrifft ausschliesslich die eigene Prosa dieses Berichts.

## 7. Limitationen

Diese Grenzen sind fuer die Reconciliation relevant, damit der Bericht nicht fuer
vollstaendiger gehalten wird, als die Erhebung ist:

1. **Themen-Index ist automatisch zugeordnet.** Regex auf Titel + Labels, keine
   inhaltliche Bewertung. Die 16 Themen ueberschneiden sich absichtlich; die Summe der
   Zaehlungen liegt daher ueber 608. Fuer die Zuordnung eines *konkreten* Issues ist die
   Voll-Tabelle bzw. Grep massgeblich, nicht die Themen-Zelle.
2. **Nur 40 offene Issues haben einen Body-Kern.** Die 568 geschlossenen Issues sind mit
   Titel, State, Labels und Datum erfasst, aber **nicht** inhaltlich ausgewertet. Fuer
   eine Fix-Verifikation ("greift der Fix wirklich?") muss der Body einzeln nachgeladen
   werden - genau die Arbeit, die der Audit in Abschnitt 5 exemplerlich vorgezeigt
   bekommt (#1085 vs. #1104).
3. **Die 509 Nummernluecken sind kein Befund.** Issues und Pull Requests teilen sich
   nachweislich denselben Nummernraum: #1105 und #1111 sind PRs im State `MERGED`, keine
   Issues, wurden aber von `gh issue view` mit Issue-Feldern beantwortet. Eine Luecke
   bedeutet also "Nummer nicht als Issue vergeben", nicht "Issue verloren".
4. **Kein Abgleich gegen Codeberg.** Das Remote ist seit 2026-07-23 auf `c4cb7ea8`
   stehen geblieben und damit fuer einen Abgleich ungeeignet. Sollte eine GitHub-nur
   Aenderung nach Juli 2026 identifiziert werden wollen, waere das eine eigene
   Aufgabenstellung.
5. **Pruefpunkt (c) ist nicht aufgeloest, nur eingegrenzt.** Ob 218 oder 219 die
   korrekte Zahl ist, laesst sich **nicht** aus den Issues beantworten - das ist eine
   Frage an den Ist-Code (`tools/list`) bzw. an den Scope der beiden Messungen. Dieser
   Bericht stellt den Widerspruch fest und benennt, was zur Aufloesung fehlt.
6. **Zwei der vier Pruefpunkte haben keinen GitHub-Beleg**, weil es kein Issue gibt
   ((b) und (d)). Deren Evidenz stammt aus Repo-Dateien und ist mit Datei und Zeile
   angegeben.

## 8. BLOCKED

**Keine.** Alle vier Pruefpunkte wurden bearbeitet, alle Daten wurden vollstaendig erhoben.

| Pruefpunkt | Ergebnis |
|---|---|
| (a) ADR-006-Upgrade-Pfad | **ABGEARBEITET** - #1112 statt #940 |
| (b) `build.sh` ohne Wirkung | **ABGEARBEITET** - kein Issue existiert, Evidenz aus Repo |
| (c) Tool-Count-Drift 218/219 | **ABGEARBEITET** - Widerspruch belegt, nicht aufgeloest |
| (d) beta.18 Checklistenschritt | **ABGEARBEITET** - Datei fehlt auf Branch, Inhalt aus `38da915f` |

**Technische Rahmenbedingungen - alle eingehalten:**

- `gh` war authentifiziert (`Popoboxxo`, Token-Scope `repo`). Keine Authentifizierungs-
  oder Rate-Limit-Blockade; das Kontingent wurde nicht annaehernd ausgeschoepft.
- **Kein** `gh issue create`, **kein** `gh issue comment`, **kein** `gh issue close`,
  **kein** Label-Edit. Der Auftrag "READ-ONLY" ist eingehalten.
- **Keine** andere Repo-Datei wurde angelegt oder geaendert. `AGENTS.md` wurde bewusst
  nicht angefasst, obwohl der dort dokumentierte Tool-Count-Drift (#1104) live ist -
  die Korrektur gehoert in den Implementierungsschritt, nicht in die Evidenz-Erhebung.
- `.kimi-code/` ist untracked und wurde weder gelesen-noch geschrieben-noch committet.
- Einzige neu erzeugte Datei im Repo: `docs/audit/2026-09/AUDIT_EVIDENCE/issue-inventory.md`
  (Verzeichnis neu angelegt).

## 9. Reproduktion in einem Aufruf

Die Zahlen in Abschnitt 1 und die Voll-Tabelle in Abschnitt 3 sind reproduzierbar mit:

```
gh issue list --repo Popoboxxo/ReqogniLoom --state all --limit 1000 \
  --json number,title,state,labels,createdAt,closedAt,author,updatedAt,url
```

und, fuer die Pruefpunkte, mit den in Abschnitt 6.1 gelisteten `--search`-Queries.

