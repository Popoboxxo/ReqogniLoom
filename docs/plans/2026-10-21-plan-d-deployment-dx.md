---
type: Plan
title: "Plan D — Deployment, DX, Onboarding (WP D1–D6) — Umsetzungsplan"
scope: "deploy/, frontend/nginx.conf, frontend/Dockerfile, frontend/public/bluepencil, backend/application/prompt_testing, .github/workflows, docs/clients, clients/registry.yaml, docs/agent-templates/INSTALL.md, README.md, scripts/, backend/auth_tenancy/management/commands/seed_demo.py"
status: proposed
date: 2026-10-21
base_head: b175c970
author_agent: senior-developer
language: de
---

# Plan D — Deployment, DX, Onboarding (D1 BluePencil, D2 Promptfoo, D3 #792, D4 Client-Doku, D5 Publikation, D6 #92/#89)

> **Reiner Umsetzungsplan. Kein Code, keine Migration, keine Config-Änderung.**
> Grundlage: Planbasis `docs/superpowers/specs/2026-10-21-backlog-umsetzungsplaene-design.md`
> (§1 Q2, §2 Plan D, §3 Wellen). Jede `datei:zeile`-Angabe ist gegen den Arbeitsbaum bei
> `b175c970` (= `origin/main`, `git rev-parse HEAD origin/main` identisch) geprüft. **Achtung:** der
> lokale Arbeitsbaum trägt uncommittete QS-Änderungen (BluePencil 0.5.0 in
> `frontend/public/bluepencil/latest/*`, `deploy/bluepencil/server.js`, untracked
> `deploy/docker-compose.sandbox.yml`); wo das relevant ist, ist `origin/main` die Referenz.
> Live-Messwerte (Check-IDs `D-L*`) von der QS (`1.8.0-beta.22`/`dc7ee14`), nur lesend; in
> Verifikationsbefehlen steht die QS-Basis-URL als Variable `$QS_URL`.
> Rohbelege: `docs/test-reports/plan-review-2026-10-21/plan-d/`. **Belege unter `docs/test-reports/`
> sind gitignored (`.gitignore:91`); DoD-Nachweise stehen im PR-Text bzw. als CI-Artefakt**
> (vorläufig, ENT-X3 = C; nach Entscheidung B Zielpfade `docs/se/reports/` bzw. `docs/reviews/`).
>
> **Verbindlich:** [Plan-Index](2026-10-21-backlog-umsetzung-index.md) (Wellen, Queues, Rollen, CI-Jobs §f.2)
> und [Korrekturaufträge](2026-10-21-korrekturauftraege.md) Abschnitt D. Offene Nutzerentscheidungen
> heißen `ENT-*` ([Entscheidungsliste](2026-10-21-entscheidungen-offen.md)). Stufe-2-Änderungen: siehe
> Abschnitt „Änderungsprotokoll Stufe 2" am Ende.

| Feld | Wert |
|---|---|
| **Status** | proposed |
| **Issues** | #1418 (D1) · #587 (D2) · #792 (D3) · #1171 (D4) · #1230 (D5) · #92, #89 (D6) |
| **Neu (Befund)** | Security-Header-Regression im Frontend-nginx (kein Issue vorhanden; D1.0) · `secret-scan` deckt Env-Geheimnisse nicht ab (QR-S03; D2.6) |
| **Wellen** | Welle 0: D1.0, D2.1–D2.5, D2.6 · Welle 2: D1.1–D1.4 · **Welle 3: D6.2** (vor Plan E E3.8, QR-T19) · Welle 4: D3–D5, D6.1 |
| **Migrations-Reservierung** | **keine** — Plan D legt keine Django-Migration an (Index §e führt Plan D nicht). |
| **A1-Gate (Q2)** | Austritt Phase P1 (siehe xiii): „Promptfoo-Gate G1–G4" laut Index §b — schaltet Plan A WP A1 frei |

---

## (i) Ziel und Nicht-Ziele

**Ziel.**
1. **D1 (#1418, B+C):** Der BluePencil-Hub läuft aus dem Upstream-Image (per Digest gepinnt); das
   vendorte `deploy/bluepencil/server.js` entfällt. Die drei Layer-Artefakte kommen per
   Read-only-Mount aus dem Deployment; im Repo bleiben Doku, Tests und die gepinnte Erwartung
   (Version + SHA256). Ein fehlender oder falscher Mount macht den Frontend-Container *unhealthy*
   und liefert 404 statt `index.html`. Vorab (D1.0): Security-Header gelten wieder für **alle**
   nginx-Antworten.
2. **D2 (#587):** `export_promptfoo_configs` + `backend/application/prompt_testing/cases/*.yaml` +
   CI-Job `prompt-regression` mit LLM-freiem Provider. Regressionsnetz für **alle** Prompt-Slots der
   Registry (Soll-Zahl = `len(get_prompt_slots())`, dynamisch — nie eine feste Zahl; QR-T07),
   **bevor** A1 Prompt-Variablen/Memory-Injektion ändert. Zusätzlich (D2.6, QR-S03): `secret-scan`
   erkennt Env-Geheimnisse im PR-Diff.
3. **D3 (#792):** RFC neu schreiben (erledigt/verworfen/offen je der 18 Punkte mit Beleg) und nur
   die offenen Punkte umsetzen (7, 12, 13, 18).
4. **D4 (#1171):** Die noch offenen der 12 „kaputten Anweisungen" und 16 Lücken schließen, mit
   Regressions-Guard im bestehenden Doku-Konsistenztest.
5. **D5 (#1230):** Externe Publikation W1–W5 als **Nutzer-Checkliste mit Gates**; Agenten erledigen
   nur repo-seitige Vorarbeit (Pin `mcp-publisher`, `server.json`-URL-Template, npm-Paket nach Gate).
6. **D6:** #92 verifizieren und schließen; #89: `seed_demo` gegen Produktionsbetrieb absichern
   (Default-Passwort nur mit explizitem Opt-in, vorläufig ENT-D9 = B).

**Nicht-Ziele.**
- Kein produktiver Review-Notes-Store (BluePencil bleibt Debug/QS-Profil, `docker-compose.yml:1560-1567`;
  vorläufig ENT-C4 = A „QS-only").
- Keine **Tenant**-Isolation im Hub (mandantenlos bleibt). **Zugriffsschutz dagegen ist Ziel** (QR-S02):
  Hub nur mit Shared Secret, nginx-Vorschaltung nur für angemeldete Sitzungen — **vorläufig, ENT-D2 = B**
  (D1.1). Bei ENT-D2 = A′ gilt stattdessen die schriftliche Risikoakzeptanz (D1.1, Variante A′).
- Kein Umbau von Prompt-Templates oder Memory-Injektion (Plan A/A1); D2 liefert nur das Netz.
- Keine Kuratierte-Store-Einreichung (E4: keine Betas), keine Accounts durch Agenten.
- Keine Neubewertung der #792-Punkte („entscheide nichts neu").
- Kein Workspace-Picker in der Key-Anlage-UI (Folge-Issue, siehe ENT-D5; Besitz Plan E).
- Präferenzdienst Q1, Memory-Port A0b/HARD_OFF, Link-Typ-Katalog: nicht Teil (Plan C/A/B/F).

## (ii) Entscheidungen (aus der Planbasis, unverändert zitiert)

| # | Wortlaut |
|---|---|
| Q2 | „**Promptfoo vor A1** (#587) — Regressionsnetz für Prompt-Variablen" |
| D1 | „BluePencil **B+C:** Hub als Image (`ghcr.io/popoboxxo/bluepencil`), `server.js` entfällt; Layer-Artefakte als Read-only-Mount, Health-Check bei fehlendem Mount" |
| D2 | „Promptfoo (`export_promptfoo_configs`, `cases/*.yaml`, CI-Job, Mock-Provider) — **vor A1**" |
| D3 | „#792 neu schreiben (≈9/18 erledigt, 4 verworfen, 5 offen), nur Offenes weiterverfolgen" |
| D4 | „Client-Doku je Harness DE/EN (12 kaputte Anweisungen, 16 Lücken)" |
| D5 | „Externe Publikation W1–W5 (Accounts, npm, MCP-Registry) — Handarbeit des Nutzers" |
| D6 | „#92 verifizieren (Workspace-Fence laut CR-03 vorhanden) und schließen; #89 Rest (`seed_demo` gegen `DEBUG=False` absichern) prüfen" |
| Welle | „Welle 0: C0, D2 (Promptfoo), G1, E2, E1" · „Welle 2: … D1" · „Welle 4: F2, F3, B6, D3–D5 und Rest" |

**Entscheidungs-Konflikte (gemeldet, nicht umgebogen):**
- **D2 „Mock-Provider":** Der ReqogniLoom-`MockLlmProvider` ignoriert den Prompt
  (`backend/llm_adapter/providers.py:415-470`, „builds no real prompt") und ist für Promptfoo nicht
  aufrufbar. Der Plan setzt „Mock" als **LLM-freien Promptfoo-Provider `echo`** um (gibt den
  gerenderten Prompt zurück) — vorläufig, ENT-D8 = A. Optionen siehe (ix) ENT-D8.
- **D6 „#92 schließen":** Fence ist vorhanden (REST+MCP), aber die UI-Anlage kennt keine
  Workspace-Auswahl (`frontend/src/api/api-keys.ts` `create(name)` sendet nur `name`). Optionen (ix) ENT-D5.
- **D6 „`seed_demo` gegen `DEBUG=False` absichern":** DEBUG ist im Dev-Overlay wahr und kann
  produktionsnah versehentlich aktiv sein (QR-S15). D6.2 erfüllt die Planbasis **und** verlangt
  zusätzlich ein explizites Opt-in — vorläufig, ENT-D9 = B. Optionen (ix) ENT-D9.
- **D1 „Hub als Image":** Das Image erzwingt ohne Konfiguration ein Auth-Secret, andere Basis,
  anderen Store-Namen und einen anderen User (D-L8) — ein 1:1-Tausch bricht den Layer. Die
  Plan-Erstfassung umging die Secret-Autogenerierung (keine Auth); das Sicherheitsreview stuft das als
  **hoch** ein (QR-S02). D1.1 setzt deshalb **vorläufig ENT-D2 = B** um (Hub mit Secret, nginx injiziert
  den Header nur nach erfolgreichem Session-Check). D1 startet erst nach Entscheidung ENT-D2
  (Entscheidungsliste: „Vorläufig: nein"); Auth-Frage (ix) ENT-D2, Rahmen ENT-C4.

## (iii) Ist-Stand (verifiziert)

### D1 — BluePencil und nginx

| Befund | Beleg |
|---|---|
| Hub = `node:22-slim` + read-only gemountetes `server.js`, Profil `bluepencil`, kein Host-Port, Store `/data/notes.json`, Basis `/bluepencil/api`, läuft als root (kein `user:`) | `deploy/docker-compose.yml:1575-1600`, Volume `:1609` |
| `origin/main` vendort Layer `0.1.0-alpha.2`, Hub `0.1.0-alpha.1`; QS liefert `0.5.0` (uncommittet) | `git show origin/main:frontend/public/bluepencil/latest/latest.json`; D-L2, D-L3 |
| QS-„0.5.0"-Layer ≠ veröffentlichtes Release v0.5.0 (attach `74709fd7…` vs. `a912e439…`, Element `a39e8868…` vs. `2fe86eda…`) | D-L9 |
| Hub-Image öffentlich: `0.5.0` = `sha256:f5c2faea…ebd95`; `hub`/`latest` = `0.8.0` = `sha256:25f4dfc6…cabf`; nur `linux/amd64`; `User: node`; Default `BLUEPENCIL_BASE=/api/v1/bluepencil`, `BLUEPENCIL_STORE=/data/notes.bluepencil.json`; Entrypoint erzeugt ohne Secret ein Auth-Secret, danach antwortet jeder Request ohne `x-bluepencil-auth` mit 401 | D-L8; `raw/hub-entrypoint-0.5.0.sh`; Hub `server.js` 0.5.0 `authorize()` |
| Browser-Bridge sendet nur `X-CSRFToken`, kein `x-bluepencil-auth` | `frontend/src/bluepencil/host.ts:52-62`; `docs/bluepencil-integration.md:86-106` |
| Loader: feste Pfade `/bluepencil/latest/{attach.js,latest.json}`, Health-Probe `/bluepencil/api/health`, Aktivierung build-time | `frontend/src/bluepencil/loader.ts:5-11,59,263-311` |
| nginx: Security-Header nur auf Server-Ebene; jede `location` mit eigenem `add_header` verliert sie (nginx-Vererbung) — betrifft `/index.html` und alle `.js/.css/…` | `frontend/nginx.conf:22-29,136-147`; D-L4, D-L5 |
| `Referrer-Policy: strict-no-referrer` ist kein gültiger Wert (Browser ignoriert ihn) | `frontend/nginx.conf:25`; D-L6 |
| `.js` mit festem Namen (`attach.js`, Element) → `Cache-Control: immutable, 1 Jahr` | `frontend/nginx.conf:144-147`; D-L4 |
| Fehlende Datei: `.js` → 404 (Regex-Location ohne `try_files`), `latest.json` → `index.html` 200 (SPA-Fallback) | `frontend/nginx.conf:131-133,144-147` |
| Image ist einziger Weg in den Docroot; Prod-Frontend ohne Volume | `frontend/Dockerfile:58`; `deploy/docker-compose.yml:1100-1139` |
| Overlay-Vertrag für lokal gebautes Frontend (#1436) + Guard-Skript | `deploy/docker-compose.yml:1101-1107`; `deploy/verify-frontend-image.sh`; `docs/DEPLOY_RUNBOOK.md:382-401` |
| Einziger Artefakt-Guard: Manifest↔Element-Bytes + `getUser`/`global path` | `frontend/src/test/bluepencil-vendor.test.ts:38-53` |
| Dev: Vite-Proxy `/bluepencil/api` → `bluepencil:8787`; `public/` direkt | `frontend/vite.config.ts:29-36`; `deploy/docker-compose.override.yml:205-217` |
| E2E-Spec existiert, skippt ohne Hub | `e2e/tests/bluepencil.spec.ts` |
| Plan G verweist R2-09 (BluePencil-Dialog `aria-modal` bei `display:none`) und den `node:22-slim`-Pin an D1 | `docs/plans/2026-10-21-plan-g-qa-haertung.md:47,409,738` |

### D2 — Promptfoo

| Befund | Beleg |
|---|---|
| Einziger Render-Pfad `resolve_and_render` existiert (Blocker aus #587 erledigt) | `backend/application/prompt_resolver.py:259-299` |
| Rendern liest DB (aktive Template-/Variablen-Zeilen) → Export braucht migrierte DB | `prompt_resolver.py:97-115,171-183` |
| System-Kontext ohne User vorhanden | `backend/auth_tenancy/context.py:153-170` (`AuthContext.system`) |
| Slot-Registry: 12 Ableitungs-/Interview-Slots + 9 `interview.protocol.*` + `memory.extract` + `architecture_decompose_tree` = 23 **am Messstand `b175c970`** (Plan B B5-T2 fügt Slots hinzu → Code und Tests nutzen nur `len(get_prompt_slots())`, QR-T07) | `backend/application/prompt_slots.py:118-149`; D-L10 |
| 8 `interview.protocol.<Typ>`-Slots werden nur als YAML geparst, nie gerendert | `prompt_slots.py:38-45`; `backend/application/interview_protocol.py:155-175,187-193` |
| `memory_context` wird automatisch injiziert, wenn deklariert und nicht übergeben (fail-open) | `prompt_resolver.py:224-256,295-298` |
| 32 Variablen live, davon 3 `config` | D-L11 |
| Keine Promptfoo-Infrastruktur im Produkt (Treffer nur `.agent-meta`) | `grep -ril promptfoo` außerhalb `.agent-meta` → nur Specs/Pläne |
| PyYAML vorhanden (transitiv, bereits genutzt) | `backend/application/interview_protocol.py:14` |
| CI: Matrix `set-1-core` = `application/tests persistence/tests`; Job-Muster `agent-templates-test` | `.github/workflows/ci.yml:38-160,248-265` |
| Promptfoo `0.124.1` (2026-10-08, MIT, Node ≥ 22.22); Exit 100 bei Testfehler; kein `--fail-on-error`; Provider `echo`; `PROMPTFOO_DISABLE_TEMPLATING`, `PROMPTFOO_DISABLE_TELEMETRY`, `PROMPTFOO_DISABLE_UPDATE` | npm-Registry; promptfoo.dev (CLI, echo, LangChain-Guide, Telemetrie) |
| Plan A erwartet `prompt_testing/cases/` + Exporter + grünen D2-Job (T-A1-8) | `docs/plans/2026-10-21-plan-a-memory-und-suche.md:319,446-450,719` |

### D3 — #792 (18 Punkte, Stand `origin/main`)

| # | Punkt | Status | Beleg |
|---|---|---|---|
| 1 | Compose-Anker / < 150 Zeilen | **verworfen** (Logging-Wiederholung begründet; Anker nur für Honcho) | `docker-compose.yml:74-77,79`; 1610 Zeilen |
| 2 | Migrate als Entrypoint | **verworfen** (One-Shot, `self_init` genau einmal) | `docker-compose.yml:826-840` |
| 3 | Backup-Command | **erledigt (anders)**: Sidecar `postgres-backup`, ADR-012 `accepted` | `docker-compose.yml:372`; `docs/se/ADR/ADR-012_backup_wahrheit.md:1-4`; `docs/DEPLOY_RUNBOOK.md:25-60` |
| 4 | Frontend `user: root`/tmpfs | **verworfen** (non-root UID 101), Ziel „läuft out of the box" erreicht | `docker-compose.yml:1113-1116` |
| 5 | Honcho Single-Stack | **erledigt** (Profil in derselben Datei) | `docker-compose.yml:19-24,1198-1500` |
| 6 | `.env.example` vollständig | **erledigt** (771 Zeilen) | `.env.example` |
| 7 | `setup.sh` | **offen** (DB-Init-Teil obsolet: App-Rolle per Migration 0048, pgvector per Migration) | kein `setup.sh`; `docker-compose.yml:635-638,861-864` |
| 8 | Systemanforderungen | **erledigt** | `README.md:198,755` |
| 9 | Root-Credentials via ENV | **erledigt** (`self_init`) | `docker-compose.yml:828-839`; `backend/application/self_init.py:70-78` |
| 10 | Embedding-Config via ENV | **erledigt** | `x-honcho-env` `docker-compose.yml:79-…` |
| 11 | LLM-Pinning via ENV | **erledigt** | `docker-compose.yml:86-108` |
| 12 | Port-Konflikt-Prüfung | **offen** (Ports parametrisiert, keine Vorprüfung) | `docker-compose.yml:717-718,1124-1125` |
| 13 | Backup vor Wipe | **offen** (nur Warnung; `down -v` löscht auch `postgres_backup_data`) | `deploy/README.md:300-310`; Off-host-Overlay `deploy/docker-compose.offhost.yml` |
| 14 | App-User = Superuser | **verworfen** (least-privilege, Migration 0048) | `docker-compose.yml:635-638` |
| 15 | `FIELD_ENCRYPTION_KEY` autogen | **verworfen** (fail-closed Pflicht) | `backend/reqogniloom/settings.py:132-138` |
| 16 | Health prüft DB/Redis | **erledigt (anders)** über ADR-010 statt Fremdpaket | `backend/reqogniloom/health.py:15-28`; D-L12 |
| 17 | Admin-Backup-Aktion | **erledigt** (REST + UI) | `backend/rest_api/urls.py:410-415`; `frontend/src/components/WorkspaceSettings/BackupRestoreSection.tsx`; D-L13 |
| 18 | Override-Warnung | **offen** (nur Kommentar; Header nennt falschen Pfad) | `docker-compose.yml:1,33-42` |

Zählung: 9 erledigt (3,5,6,8,9,10,11,16,17), 6 verworfen (1,2,4,14,15 + 16-Weg), offen 4 (7,12,13,18).
Planbasis „9/4/5" und Kommentar „~9/6/5" zählen 4/16 und 17 unterschiedlich; **keine Neubewertung**,
die Tabelle oben ist der Beleg für die Neufassung (D3.1).

### D4 — #1171 (12 kaputte Anweisungen laut Kommentar 13.10., Stand heute)

| ID | Anweisung | Status | Beleg |
|---|---|---|---|
| K1 | `docker-compose` statt `docker compose` | behoben (#1293) | 0 Treffer; Guard `docs/agent-templates/test_doc_surface_consistency.py:85` |
| K2 | `export_tool_manifest` → `PermissionError /docs` | behoben | `docs/agent-templates/INSTALL.md:129-136` |
| K3 | `python` statt `python3` | **teilweise offen** | `docs/clients/STAGE2.md:23`, `STAGE2.de.md:23` (Host-Befehl); nicht in `SHELL_COMMAND_DOCS` (`test_doc_surface_consistency.py:54-58`) |
| K4 | `opencode mcp add` ohne `--header` | behoben | `INSTALL.md:45-46`; CLI 1.18.35 hat `--header` (D-L17) |
| K5 | Regenerierung nennt Codex-Builder nicht | **offen** | `INSTALL.md:137-142` vs. `dist/codex/build_codex_package.py` |
| K6 | Health-Ausgabe/Pfad `/health/` | behoben | `README.md:37,519` |
| K7 | Claude-Desktop `YOUR_API_KEY` + curl-SSE | **offen** | `README.md:428-446` |
| K8 | Antigravity ohne `"type":"sse"` | behoben | `docs/clients/antigravity.md`, `clients/registry.yaml` |
| K9 | veraltete Toolzahl | behoben (Zahl per Guard gegen Manifest geprüft) | `test_doc_surface_consistency.py:46-51` |
| K10 | `install.sh` Codex ohne Bearer-Var | behoben | `scripts/clients/install.sh:194-200` |
| K11 | `install.sh` Skills-Dir CWD-relativ | behoben | `scripts/clients/install.sh:142-160` |
| K12 | `opencode.json` statt `opencode.jsonc` | **offen** | `INSTALL.md:52-53,83`; `docs/clients/opencode.md:72` |
| K13 (neu) | README-Beispiele Cursor/Claude Desktop auf `/mcp/stdio/` (404), Port 8000, `reqlo_`-Beispiel-Key | **offen** | `README.md:1213-1250`; D-L15 |
| K14 (neu) | `claude mcp add --transport http` auf `/mcp/sse/` (Plugin nutzt `type: sse`) | **offen** | `docs/clients/claude-code.md:33-37` vs. `dist/plugins/claude-code/reqogniloom/.mcp.json` |

**16 Lücken** — der Kommentar nennt 4 (+2 im Nachtrag); das Audit-Dokument
(`/opt/data/reqogniloom-env/qa-beta20/INSTALL_DOKU_AUDIT.md`) liegt nicht auf diesem Host (NICHT
PRÜFBAR). Die Liste ist daher aus Kommentar + Issue-Body §2 abgeleitet:

| ID | Lücke | Status | Beleg |
|---|---|---|---|
| L1 | `x-opencode-session` undokumentiert | behoben (Betreiberseite) | `README.md` (4 Treffer), `deploy/README.md:128` |
| L2 | Modell/Provider in `INSTALL.md` und README §9 | **offen** (nur in `docs/clients/*`) | `INSTALL.md` Abschnitte nur Claude/OpenCode/Antigravity (`:9,37,93`) |
| L3 | Drei Platzhalterformen nicht gegenübergestellt | **offen** | `YOUR_API_KEY` nur `README.md:439`; keine Tabelle |
| L4 | Antigravity `pclmulqdq` | behoben | `docs/clients/antigravity.md:57` |
| L5 | Hermes-Desktop-Plugin | behoben | `docs/clients/hermes.md:50-105` (+ DE) |
| L6 | Hermes Toolzahl | behoben | Guard |
| L7 | Claude: öffentlicher Marketplace-Weg | **offen bis W1** | `docs/clients/claude-code.md:22-26` nur lokal |
| L8 | Claude: `plugin validate` | **offen** (nicht in CI) | nur `STAGE2.md:23`; kein Workflow-Treffer |
| L9 | Claude: Env-Werte beim Install | **offen** — `userConfig` wird unterstützt | Claude-Code-Doku „Plugin manifest reference" (userConfig, `${user_config.KEY}`); `plugin.json` ohne `userConfig` |
| L10 | Codex: `codex mcp add` als Primärweg | **teilweise** (nur via `install.sh`) | `docs/clients/codex.md:20-27` |
| L11 | Codex: Plugin-Marketplace | **offen bis W4** | `STAGE2.md:30` |
| L12 | OpenCode: `opencode plugin`/`agent create` | `plugin` als Stufe 2 erwähnt, `agent create` **offen** | `docs/clients/opencode.md:72` |
| L13 | Kimi komplett fehlend | behoben | `docs/clients/kimi-code.md` |
| L14 | Antigravity Verify-Kommando | **offen** (Prosa statt Befehl, deutsch in EN-Seite) | `docs/clients/antigravity.md:49-53` |
| L15 | Hermes MCP-Rezept | behoben | `docs/clients/hermes.md` (`hermes mcp test`) |
| L16 | Transport-Entscheidungshilfe | behoben | `docs/clients/README.md` „Transport decision" |

Zusatz: `INSTALL.md:166-170` behauptet, Codex habe keinen Header-Mechanismus — Codex 0.151.0 kennt
`env_http_headers`/`http_headers` (Binär-Strings, D-L17). Generierte Seiten: Quelle ist
`clients/registry.yaml` + `scripts/clients/render.py` (`render.py --check` in
`.github/workflows/client-artifacts-check.yml:57`).

### D5 — #1230

| Befund | Beleg |
|---|---|
| `server.json` Remote-URL `https://<host>/mcp/` (literal), erzeugt von `render.py:388` | `server.json:13`; Schema 2025-12-11 erlaubt `{var}` + `variables` (`RemoteTransport`) |
| `mcp-publisher` über `releases/latest/download`, ungepinnt (TODO im Workflow) | `.github/workflows/publish-mcp-registry.yml:20,77,92-96`; aktuell v1.8.1, `mcp-publisher_linux_amd64.tar.gz` SHA256 `a06c9096dcb9727c13555b6be26c7effa707b01f06a4c561ba7a3635443cf2cc` (`raw/mcp-registry-1.8.1-checksums.txt`) |
| npm-Workflow inert, `PACKAGE_DIR=dist/npm/reqogniloom-opencode` existiert nicht | `.github/workflows/publish-npm.yml:81-119`; `dist/npm` fehlt |
| npm-Paket/Org nicht vorhanden; Registry-Suche nicht prüfbar | D-L16 |
| Repo öffentlich; Marketplace-Datei vorhanden | `gh repo view` → `PUBLIC`; `.claude-plugin/marketplace.json` |

### D6 — #92, #89

| Befund | Beleg |
|---|---|
| `ApiKey.workspace_ids` (+ `scope`, `principal_type`, `expires_at`) | `backend/auth_tenancy/models.py:144-162`; Migration `0013_apikey_agent_identity.py` |
| Fence REST+MCP gemeinsam, Default an (ADR-011 **SEC-03**, nicht CR-03) | `backend/auth_tenancy/resource_scope.py:60-80,711-716`; `settings.py:683-684` |
| Tests vorhanden | `backend/rest_api/tests/test_sec02_sec03_workspace_fence.py`; `backend/mcp_server/tests/test_mcp_workspace_fence_1376.py` |
| REST-Anlage nimmt `workspace_ids`; UI sendet nur `name` | `backend/rest_api/api_key_views.py:324-369`; `frontend/src/api/api-keys.ts` `create(name)` |
| Live: gefencter Agent-Key existiert | D-L14 |
| UUID-Anzeige/Copy + MCP-Panel erledigt (#92 Pkt. 2/3) | `frontend/src/components/WorkspaceSettings/McpConnectionSection.tsx:33-34,234-303` |
| `seed_demo`: Default-Passwort `admin12345` ohne Umgebungsprüfung; druckt Passwort | `backend/auth_tenancy/management/commands/seed_demo.py:41,73-78,123-126` |
| Docstring nennt nicht mehr existenten `bootstrap`-Service | `seed_demo.py:5-7` vs. `docker-compose.yml:831-833` |
| CI ruft `seed_demo` (Kommentar-Frage beantwortet), Login kommt aber aus `self_init` (`SYSTEM_ADMIN_PASSWORD` im Migrate-Step) | `.github/workflows/playwright.yml:107-115` |
| CI/Dev: `DEBUG` effektiv `True` (`DJANGO_ENV=test`/`development`); Prod: `DEBUG` hart `False` | `playwright.yml:79-80`; `deploy/docker-compose.override.yml:55-56`; `settings.py:65-68` |
| README: `seed_demo` „creates demo artifacts" (falsch: nur Tenant/Workspace/Admin) und Prod-Aufruf | `README.md:281-293,803-806` |

## (iv) Arbeitspakete und Tasks

Konventionen: Backend-Tests gegen echte DB (pytest-django), lokal nur gezielt; Testbefehl gegen den
Dev-Stack = Makro aus Index §f.3. Neue Tests unter `scripts/test_*.py` laufen in CI nur, wenn der PR sie
an den Job `agent-templates-test` anbindet (Index §f.4, RB-D18) — Plan D tut das je Task explizit.
Compose-Verträge werden wie
`backend/memory/tests/test_honcho_deploy_contract.py` per `yaml.safe_load` gepinnt. Live-Verifikation
auf QS nur lesend. „TDD" = genannter Test zuerst, rot gegen `b175c970`.

### WP D1 — BluePencil B+C und nginx (D1.0 Welle 0, Rest Welle 2; D1.1–D1.4 erst nach ENT-D2)

#### D1.0 — Security-Header für alle nginx-Antworten (devops-engineer, Review security-auditor)

- **Anlass:** RB-D02, RB-D16. Kein Issue vorhanden → vor PR per `feedback`-Agent Issue anlegen
  („nginx: security headers lost in locations with add_header — regression of #155"), PR `Fixes #<neu>`.
- **Neu:** `frontend/nginx-security-headers.conf` (die fünf `add_header … always;` aus
  `nginx.conf:23-29`, `Referrer-Policy "strict-origin-when-cross-origin"` — entspricht dem heute
  effektiven Browser-Default, daher keine Verhaltensänderung für CSRF-Referer-Prüfungen).
- **Ändern:** `frontend/nginx.conf`: Server-Ebene `include /etc/nginx/snippets/security-headers.conf;`
  statt der Einzelzeilen; zusätzlich `include` in **jeder** `location` mit eigenem `add_header`
  (`= /healthz` `:32-36`, `= /index.html` `:136-140`, Regex-Assets `:144-147`).
  `frontend/Dockerfile:60` (nach `COPY nginx.conf`): `COPY nginx-security-headers.conf /etc/nginx/snippets/security-headers.conf`.
- **Neu:** `frontend/scripts/check-nginx-headers.sh <base-url>` — `curl -sD -` auf `/`, `/requirements`,
  `/assets/<erste .js aus index.html>`, `/healthz`; je Antwort Pflicht: `Content-Security-Policy`,
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`; Exit 1 mit Pfad+fehlendem Header.
  **Zusätzlich (QR-S17, KA-D-07):** die CSP enthält `frame-ancestors 'none'` (fehlt heute,
  `nginx.conf:29` → im Snippet ergänzen) und die `script-src`-Direktive enthält weder `'unsafe-inline'`
  noch `'unsafe-eval'`; Verstoß → Exit 1 mit Direktive im Text.
- **CI (neu, `.github/workflows/ci.yml`):** Job `nginx-headers-smoke` (ohne Pfadfilter): legt `$RUNNER_TEMP/www`
  mit `index.html` (ein `<script src="/assets/a.js">`) und `assets/a.js` an; `docker run -d -p 8080:8080`
  `nginx:1.27-alpine@sha256:<digest>` (**per Digest gepinnt**, Digest ermittelt der Implementierer mit
  `docker buildx imagetools inspect nginx:1.27-alpine` und trägt Tag-Kommentar daneben ein) mit
  `frontend/nginx.conf` → `/etc/nginx/conf.d/default.conf:ro`, Snippet →
  `/etc/nginx/snippets/security-headers.conf:ro`, `www` → `/usr/share/nginx/html:ro`;
  `docker exec … nginx -t`; dann `bash frontend/scripts/check-nginx-headers.sh http://localhost:8080`.
  **Negativfall im selben Job:** zweiter Container mit einer Snippet-Kopie, in der `script-src` um
  `'unsafe-inline'` erweitert ist → Skript muss Exit 1 liefern (Schritt invertiert: Job rot, wenn Exit 0).
- **TDD:** zuerst den CI-Job mit unverändertem `nginx.conf` → rot (`/: missing Content-Security-Policy`).
- **DoD:** Job grün (inkl. Negativfall); nach QS-Deploy `bash frontend/scripts/check-nginx-headers.sh "$QS_URL"`
  → Exit 0; Browser-Konsole (Playwright-MCP `browser_console_messages`) auf `/`, `/requirements`,
  `/architecture`, `/settings`, `/system-settings` ohne CSP-Verletzung (CSP gilt erstmals für das Dokument).
- **Regel bei CSP-Verletzung (QR-S17):** Revert des PR. `script-src` wird **nie** aufgeweicht
  (`'unsafe-inline'`/`'unsafe-eval'` verboten, Gate im Skript); zulässig ist nur das Ergänzen einer
  konkreten, nicht-skriptbezogenen Quelle mit Begründung im PR.
- **Check-Name:** `nginx-headers-smoke` entsteht mit diesem PR (P1-1) und gilt erst nach dessen Merge als
  „grün auf"-Check für andere PRs (Index §f.2).

#### D1.1 — Hub aus dem Image (B) mit Zugriffsschutz (devops-engineer, Review security-auditor)

- **Eintritt:** ENT-D2 entschieden (Entscheidungsliste „Vorläufig: nein"); P1-1 (D1.0) gemergt;
  Plan A PR-A2 gemergt (Compose-Queue, Index §d.2, QR-T20). Rahmen: ENT-C4 (vorläufig A, QS-only).
- **Fassung unten = vorläufig, ENT-D2 = B** (Empfehlung Sicherheitsreview QR-S02). Variante A′ am Ende
  der Task.
- **Ändern `deploy/docker-compose.yml:1575-1600`** (Service `bluepencil`):
  - `image: ${BLUEPENCIL_HUB_IMAGE:-ghcr.io/popoboxxo/bluepencil:0.5.0@sha256:f5c2faea6db2c3452dd90275dc587c82352e9ebceabcb642b32c434f205ebd95}` (vorläufig, ENT-D1 = A).
  - **Image-Entrypoint bleibt aktiv** (kein `entrypoint:`-Override mehr). Konfiguration per Env:
    `BLUEPENCIL_AUTH_SECRET: ${BLUEPENCIL_AUTH_SECRET:?set BLUEPENCIL_AUTH_SECRET for the bluepencil profile}`,
    `BLUEPENCIL_BASE: /bluepencil/api`, `BLUEPENCIL_STORE: /data/notes.json` (Store-Dateiname bleibt →
    Notizen bleiben erhalten), `BLUEPENCIL_NAME: reqogniloom`, `BLUEPENCIL_PORT: "8787"`;
    `command: ["--environment", "${BLUEPENCIL_ENVIRONMENT:-dev}"]` (der Entrypoint hängt `"$@"` an).
    Ist das Secret per Env gesetzt, schreibt der Entrypoint es **nicht** ins Log (nur im
    Autogenerier-Zweig; `raw/hub-entrypoint-0.5.0.sh:29-50`, Rohbeleg gitignored) — Contract-Test sichert,
    dass der Env-Zweig genutzt wird.
  - Kein `ports:` (kein Host-Port), wie heute.
  - Volume `./deploy/bluepencil/server.js:…` **entfernen**; `bluepencil_data:/data` bleibt.
  - Healthcheck: `node`-fetch auf `/bluepencil/api/health` **mit** Header `x-bluepencil-auth` aus der Env
    (falls `authorize()` 0.5.0 `/health` nicht ausnimmt — Implementierer prüft das am Image).
  - `depends_on: {bluepencil-volume-init: {condition: service_completed_successfully}}`.
- **Ändern `frontend/nginx.conf` → Template** (`location /bluepencil/api/`, heute `:118-128`):
  - `auth_request /_bluepencil_auth;` — interne Location `location = /_bluepencil_auth { internal;
    resolver 127.0.0.11 ipv6=off valid=10s; set $auth_upstream http://backend:8000/api/v1/auth/me/;
    proxy_pass $auth_upstream; proxy_pass_request_body off; proxy_set_header Content-Length "";
    proxy_set_header Cookie $http_cookie; proxy_set_header Authorization $http_authorization; }`.
    `GET /api/v1/auth/me/` (`backend/rest_api/urls.py:305`) akzeptiert das httpOnly-Access-Cookie
    (`backend/auth_tenancy/rest.py:88,186`); ohne Sitzung → 401, nginx antwortet 401.
  - `proxy_set_header x-bluepencil-auth "${BLUEPENCIL_AUTH_SECRET}";` — Wert per envsubst aus dem
    nginx-Template-Mechanismus des Basis-Images (`/etc/nginx/templates/default.conf.template`,
    `NGINX_ENVSUBST_FILTER=^BLUEPENCIL_`, damit nginx-eigene `$`-Variablen unberührt bleiben).
    `frontend/Dockerfile:60`: `COPY nginx.conf /etc/nginx/templates/default.conf.template`,
    `ENV BLUEPENCIL_AUTH_SECRET=""` (leer → Hub antwortet 401, fail-closed), `chown app:app /etc/nginx/conf.d`
    (Image läuft als `app`, envsubst schreibt dorthin). Der Header des Clients wird überschrieben, nie
    durchgereicht.
  - Smoke-Job `nginx-headers-smoke` (D1.0) mountet ab diesem PR die Datei als Template und setzt
    `BLUEPENCIL_AUTH_SECRET=smoke-dummy` (kein echtes Geheimnis).
  - Das Secret steht **nur** in `.env` bzw. als Compose-Secret, nie in Logs, nie im Repo; `deploy/docker-compose.bluepencil.yml`
    (D1.2) reicht es an den Frontend-Container durch.
- **Sandbox:** der untracked `deploy/docker-compose.sandbox.yml` publiziert den Hub-Port ins LAN
  (`:131`) — Port-Zeile entfernen bzw. Datei nicht committen (Index §h, Hinweis an Betreiber im PR).
- **Neu (gleiche Datei):** Service `bluepencil-volume-init`: gleiches Image, `profiles: ["bluepencil"]`,
  `user: "0"`, `entrypoint: ["chown", "-R", "node:node", "/data"]`, `restart: "no"`,
  Volume `bluepencil_data:/data`. Grund: bisheriger Store gehört root, das Image läuft als `node` (RB-D01).
- **Löschen:** `deploy/bluepencil/server.js`.
- **Ändern:** `.env.example` (Abschnitt BluePencil, `:634-637`): `BLUEPENCIL_HUB_IMAGE` und
  `BLUEPENCIL_AUTH_SECRET=CHANGE-ME…` (Erzeugung `openssl rand -hex 32`) dokumentiert, Hinweis
  „nur linux/amd64" (RB-D06); `Makefile:61` Hilfetext („sidecar" → „hub image").
- **TDD:** `backend/tests/test_bluepencil_deploy_contract.py` (läuft in `set-4-features`, Pfad `tests`):
  `test_hub_image_is_digest_pinned` (Default enthält `@sha256:`), `test_hub_runs_with_auth_secret`
  (kein `entrypoint`-Override; `BLUEPENCIL_AUTH_SECRET` ist Pflicht-Interpolation `:?`, kein Default-Wert),
  `test_hub_keeps_store_path_and_base` (`/data/notes.json`, `/bluepencil/api`),
  `test_hub_publishes_no_host_port`, `test_volume_init_runs_before_hub`,
  `test_no_vendored_server_js` (`deploy/bluepencil/server.js` existiert nicht),
  `test_nginx_bluepencil_location_requires_auth_request` (liest `frontend/nginx.conf`: Location
  `/bluepencil/api/` enthält `auth_request` und `proxy_set_header x-bluepencil-auth`; interne Auth-Location
  ist `internal`).
- **DoD:** Tests grün; QS-Gate vor/nach Umstellung (Betreiber, mit angemeldeter Sitzung `-b "$QS_COOKIE"`):
  `curl -s -b "$QS_COOKIE" "$QS_URL/bluepencil/api/notes" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))'`
  liefert vorher = nachher (Erwartung QS: Wert laut #1418); **Smoke ohne Sitzung:**
  `curl -s -o /dev/null -w '%{http_code}' "$QS_URL/bluepencil/api/notes"` → `401`, mit Sitzung → `200`;
  `curl -s -b "$QS_COOKIE" "$QS_URL/bluepencil/api/health"` → `{"ok":true,…,"version":"0.5.0"}`;
  `e2e/tests/bluepencil.spec.ts` grün mit `make bluepencil` (gezielte Spec, kein voller Lauf).
- **Variante A′ (nur falls ENT-D2 = A′):** Entrypoint-Override `["node","/app/server.js"]` statt Secret,
  keine nginx-Änderung; dafür im Plan und im PR-Text eine **schriftliche Risikoakzeptanz** des Nutzers
  (unauthentifizierte, mandantenlose Notiz-API inkl. Hub-MCP am Frontend-Port), Profil `bluepencil`
  nur auf QS, Sandbox-Port entfernt; `test_hub_runs_with_auth_secret` und
  `test_nginx_bluepencil_location_requires_auth_request` entfallen, `test_hub_publishes_no_host_port` bleibt.

#### D1.2 — Layer aus dem Deployment (C) mit Pin, Fetch und fail-closed Auslieferung (devops-engineer + frontend-component-engineer)

- **Neu `deploy/bluepencil/layer.lock.json`:**
  `{"version":"0.5.0","release":"https://github.com/Popoboxxo/bluepencil/releases/download/v0.5.0/","assets":{"attach.js":"a912e439b01388cfa85eed7f0f336d76ca363f4a8840e31a6a96e19af74e2d01","bluepencil.element.min.js":"2fe86edaa9d42a38615d92b02a765204ade071d2dcb9f66cc13e7a76fb065d26"}}`
  (Release-Bytes, nicht QS-Bytes — RB-D03; vorläufig ENT-D3 = A).
- **Neu `deploy/bluepencil/fetch-layer.sh [--dest DIR]`** (Default `deploy/bluepencil/layer`):
  lädt `attach.js`, `bluepencil.element.min.js`, `SHA256SUMS` aus `release`, prüft (a) gegen
  `SHA256SUMS`, (b) gegen den Lock, (c) `grep -q getUser` und `grep -q "global path"` im Element
  (#988-Guard), schreibt `latest.json` `{"version","element":"bluepencil.element.min.js","sha256"}`
  atomar (tmp + `mv`). Exit 1 bei jeder Abweichung, nichts halb geschrieben.
- **Löschen:** `frontend/public/bluepencil/latest/{attach.js,bluepencil.element.min.js,latest.json}`.
  **`.gitignore`:** `frontend/public/bluepencil/`, `deploy/bluepencil/layer/` (RB-D23: verhindert
  erneutes Einchecken unklarer Bytes; Betreiber entfernt lokale Reste per `fetch-layer.sh`).
- **Ändern `frontend/nginx.conf`:** neue Location vor `location /`:
  `location ^~ /bluepencil/latest/ { try_files $uri =404; include /etc/nginx/snippets/security-headers.conf; add_header Cache-Control "no-cache" always; }`
  (`^~` schlägt die Regex-Asset-Location → kein `immutable`, fehlende Datei = 404 statt `index.html`; RB-D04, RB-D05).
- **Neu `deploy/docker-compose.bluepencil.yml`** (Overlay, ersetzt das bisher nur dokumentierte
  QS-Muster): `frontend.image: ${BLUEPENCIL_FRONTEND_IMAGE:?set to the locally built frontend image with VITE_BLUEPENCIL_ENABLED=1}` (#1436-Vertrag);
  `frontend.environment.BLUEPENCIL_AUTH_SECRET: ${BLUEPENCIL_AUTH_SECRET:?…}` (für den nginx-Header aus D1.1;
  bei ENT-D2 = A′ entfällt die Zeile);
  Volume Langform `type: bind`, `source: ${BLUEPENCIL_LAYER_DIR:-./deploy/bluepencil/layer}`,
  `target: /usr/share/nginx/html/bluepencil/latest`, `read_only: true`,
  `bind: {create_host_path: false}` (fehlender Pfad = Compose-Fehler statt leerem Verzeichnis);
  Healthcheck:
  `CMD-SHELL d=/usr/share/nginx/html/bluepencil/latest; test -s $$d/attach.js && h=$$(sha256sum $$d/bluepencil.element.min.js | cut -d' ' -f1) && grep -q "$$h" $$d/latest.json && curl -fsS http://localhost:8080/healthz >/dev/null`.
- **Ändern `deploy/verify-frontend-image.sh`:** Vergleich gegen `deploy/bluepencil/layer.lock.json`
  (Version + Element-SHA) statt gegen die gelöschte Repo-Datei (`REPO_LAYER`, Z. 26).
- **Ändern `frontend/src/test/bluepencil-vendor.test.ts`:** zusätzlich `manifest.version === lock.version`
  und `manifest.sha256 === lock.assets["bluepencil.element.min.js"]`; Test liest Dateien aus
  `public/bluepencil/latest` (unverändert).
  **CI `frontend-test`** (`ci.yml:343-365`): Schritt vor Vitest
  `bash deploy/bluepencil/fetch-layer.sh --dest frontend/public/bluepencil/latest` — echte Release-Bytes,
  kein Mock.
- **Ändern `Makefile`:** Ziel `bluepencil-layer` (`fetch-layer.sh --dest frontend/public/bluepencil/latest`),
  `bluepencil` hängt davon ab (Dev serviert `public/` über Vite).
- **TDD:** (1) `check-nginx-headers.sh` um `--bluepencil` erweitert: `/bluepencil/latest/missing.json`
  → 404, `/bluepencil/latest/latest.json` → `Cache-Control: no-cache` + Security-Header; der
  Smoke-Job aus D1.0 legt dafür eine Datei `bluepencil/latest/latest.json` an → rot vor der Location.
  (2) `backend/tests/test_bluepencil_deploy_contract.py::test_layer_overlay_mount_is_readonly_and_not_autocreated`.
  (3) `fetch-layer.sh` mit manipuliertem Lock (Test-Schritt im `frontend-test`-Job, `--lock <tmp>` mit
  falschem SHA) → Exit 1.
- **DoD:** alle drei grün; QS: `curl -s "$QS_URL/bluepencil/latest/latest.json"` → `"version": "0.5.0"`,
  `sha256 == 2fe86eda…`; `curl -sD - -o /dev/null "$QS_URL/bluepencil/latest/attach.js" | grep -i cache-control`
  → `no-cache`; Browser-Event `bp-attach-ready` mit `"version":"0.5.0"` (Lock-Version vorläufig, ENT-D1 = A /
  ENT-D3 = A).

#### D1.3 — Doku Auslieferungsvertrag (documenter)

- **Ändern:** `docs/bluepencil-integration.md` §5 „Build-Pin und Asset-Integrität" → „Auslieferungsvertrag
  (B+C)": Hub-Image + Digest, Zugriffsschutz (Shared Secret im Hub, nginx `auth_request` + Header-Injektion;
  vorläufig ENT-D2 = B — bei A′ stattdessen Risikoakzeptanz), Layer-Mount, Lock, Fetch, Cache-Policy,
  fail-closed-Health; `deploy/bluepencil/README.md:178-212` (Versionsstand, Upgrade-Rezept =
  Lock-Bump + `fetch-layer.sh` + Digest-Bump); `deploy/README.md` (Overlay-Abschnitt #1436 → neues
  Overlay); `docs/DEPLOY_RUNBOOK.md:382-401`.
- **DECISION-Block** (für `documenter`):
  context: Layer-Updates erzwangen Image-Rebuild, Hub war vendort und unauthentifiziert · choice: Hub-Image
  per Digest mit Shared Secret, nginx gibt `/bluepencil/api/` nur nach Session-Check frei (vorläufig ENT-D2 = B),
  Layer per gepinntem Release-Fetch + Read-only-Mount · alternatives: A Status quo (Rebuild je Update),
  nur B (Layer bleibt im Image), Entrypoint-Umgehung ohne Auth (abgelehnt, QR-S02) · consequences:
  Layer-Update = Lock-Bump ohne Rebuild; neuer Laufzeitvertrag (Mount + Secret), abgesichert durch
  Healthcheck/404/401 · design_vs_speed: kleiner Mehraufwand
  jetzt, spart je Upstream-Release einen Frontend-Build auf engen Hosts.
- **DoD:** `grep -rn "server.js" docs/bluepencil-integration.md deploy/README.md deploy/bluepencil/README.md`
  → nur historische Erwähnung mit „removed in D1".

#### D1.4 — Upstream R2-09 + Issue-Abschluss (user / feedback)

- R2-09 (`aria-modal="true"` an verborgener Legende, #1406) als Issue in `Popoboxxo/bluepencil` melden
  (Fremdkomponente); nach Upstream-Fix Lock-/Digest-Bump als eigener Kleinst-PR.
- #1418 mit Kommentar „B+C umgesetzt, PR …" schließen. **DoD:** Upstream-Issue-Link in #1406 vermerkt.

### WP D2 — Promptfoo-Regressionsnetz (Welle 0, vor A1)

#### D2.1 — Fall-Format, Loader, eine Fall-Datei je Registry-Slot (developer)

- **Neu:** `backend/application/prompt_testing/__init__.py`, `backend/application/prompt_testing/cases.py`:
  - `@dataclass(frozen=True) class PromptScenario: name: str; data: dict[str, Any]; config: dict[str, Any]; asserts: tuple[dict[str, Any], ...]; deep_asserts: tuple[dict[str, Any], ...]`
  - `CASES_DIR: Path = Path(__file__).parent / "cases"`
  - `DETERMINISTIC_ASSERT_TYPES = frozenset({"contains","not-contains","icontains","not-icontains","contains-all","contains-any","regex","not-regex","starts-with","equals","javascript"})`
  - `def load_cases(cases_dir: Path = CASES_DIR) -> dict[str, list[PromptScenario]]` — Datei
    `<slot_name>.yaml` (Slot-Name = Dateiname ohne `.yaml`), Schema:
    ```yaml
    slot: need_to_sysreq
    scenarios:
      - name: payment-with-memory
        data: {need_title: "Zahlung", need_description: "…", memory_context: "## Memory\n- Zahlungen in EUR"}
        config: {max_requirements_per_need: 3}
        assert:
          - {type: contains, value: "Zahlung"}
          - {type: contains, value: "Zahlungen in EUR"}
        deep_assert:
          - {type: llm-rubric, value: "…"}
    ```
    Fehler (`CaseFormatError`): `slot` ≠ Dateiname, unbekannter Assert-Typ in `assert`,
    `llm-rubric` außerhalb `deep_assert` (RB-D09), leere `scenarios`.
  - **Besitz- und Erweiterungsregel (QR-T05/T06/T07, Index §b):** Die Case-Dateien gehören Plan D. Andere
    Pläne **erweitern** sie um Szenarien (Plan A T-A1-8) bzw. legen nur für **neue** Slots eine Datei im
    **selben PR** wie den Slot an (Plan B B5-T2: `quality_*`-Dateien). In `main` wird nie ein roter Case
    gemergt; rote Baseline-Nachweise stehen nur im PR-Text. Top-k-/Format-Prüfungen gehören in
    `application/tests/test_prompt_resolver.py`, nicht in Promptfoo. Die Regel steht als Kommentarkopf in
    `cases.py` und im Docstring von `test_every_slot_has_exactly_one_case_file`.
- **Neu:** `backend/application/prompt_testing/cases/<slot>.yaml` für **jeden** Slot aus
  `get_prompt_slots()` (am Messstand 23, D-L10, RB-D11 — Soll-Zahl im Code und in Tests nie hart codiert).
  Pflicht je gerendertem Slot: ein Szenario mit leerem `memory_context` und — sofern der Factory-Body
  `{memory_context}` enthält — eines mit befülltem Block + `contains` auf den Block. Für die 8
  `interview.protocol.<Typ>`-Slots: ein Szenario mit `contains: "phases:"`; die YAML-Gültigkeit prüft
  der Test (nicht Promptfoo).
- **TDD:** `backend/application/tests/test_prompt_testing_cases.py`:
  `test_every_slot_has_exactly_one_case_file` (Menge `get_prompt_slots()` == Dateinamen, keine Waisen;
  `assert len(files) == len(get_prompt_slots())` — keine feste Zahl; Docstring: „Case files are owned by
  plan D. A new prompt slot ships its case file in the same PR; other plans extend existing files with
  scenarios. Never merge a red case into main."),
  `test_case_format_errors_are_reported` (tmp-Dir mit Fehlerfällen),
  `test_every_scenario_renders_without_unresolved_placeholders` (echter `resolve_and_render`,
  `db`-Fixture, Nil-Tenant; `extract_placeholders(rendered)` ∩ (Daten-Variablen ∪ Config-Namen) = ∅),
  `test_memory_slots_cover_a_filled_memory_block`,
  `test_protocol_defaults_are_valid_protocols` (bestehender Validator, `interview_protocol.py:43`).
- **DoD:** 5 Tests grün in `set-1-core`.

#### D2.2 — `export_promptfoo_configs` (developer)

- **Neu:** `backend/application/management/commands/export_promptfoo_configs.py`.
  Argumente: `--out PATH` (Default `<repo>/promptfoo/generated`; im Container `--out /tmp/pf`, da
  `/app/docs`-Mounts read-only sind, vgl. `INSTALL.md:129-133`), `--cases-dir PATH`, `--slot NAME`
  (wiederholbar), `--check` (nichts schreiben, nur prüfen), `--deep` (zusätzlich `deep_assert`, Provider aus
  `--provider`, z. B. `anthropic:messages:<modell>`; nie in CI — **technisch erzwungen:** bei gesetzter
  Umgebungsvariable `CI` (`true`/`1`) bricht `--deep` mit `CommandError("--deep is refused in CI")` ab, QR-S12).
  Provider im Export: `echo` (vorläufig, ENT-D8 = A).
- Ablauf je Szenario: `TenantContext.set_tenant(UUID(int=0))` (`persistence/tenancy.py:52`), `ctx =
  AuthContext.system(tenant_id=UUID(int=0))`, `resolve_and_render(slot, ctx, None,
  config_overrides=scenario.config, **scenario.data)`; `finally: TenantContext.clear_tenant()`.
  Nil-Tenant hat keine Zeilen → Factory-Defaults (deterministisch).
- Ausgabe `<out>/<slot>.promptfooconfig.yaml`:
  ```yaml
  description: "reqogniloom prompt slot <slot>"
  prompts: [{id: "<slot>::<scenario>", raw: "<gerenderter Prompt, literal>"}]   # je Szenario
  providers: [echo]
  tests: [{description: "<scenario>", options: {prompt: "<slot>::<scenario>"}, assert: [...]}]
  ```
  (Zuordnung Szenario↔Prompt über `prompts`-Filter je Test; Implementierer verifiziert Feldnamen gegen
  promptfoo 0.124.1 im ersten Lauf — Abweichung = Anpassung des Exporters, nicht der Fälle.)
- Letzte Ausgabezeile (stabil, maschinenlesbar):
  `promptfoo export: <n>/<len> slots, <m> missing cases, <u> unresolved placeholders, memory slots covered <a>/<b>`
  mit `<len> = len(get_prompt_slots())` (dynamisch, **nie** 23; QR-T07);
  Exit 1, wenn `n < len`, `m > 0`, `u > 0` oder `a < b`.
- **TDD:** `backend/application/tests/test_export_promptfoo_configs.py`:
  `test_writes_one_config_per_slot` (`call_command` → `assert len(files) == len(get_prompt_slots())`,
  `yaml.safe_load`, `providers==["echo"]`, kein `{data_var}` im `raw`),
  `test_check_fails_on_missing_case` (`--cases-dir` ohne eine Datei → `CommandError`),
  `test_deep_asserts_only_with_deep`, `test_summary_line_format` (Regex mit `(\d+)/(\d+) slots`, zweite Zahl
  == `len(get_prompt_slots())`), `test_deep_refused_in_ci` (`monkeypatch.setenv("CI", "true")` + `--deep` →
  `CommandError`; QR-S12).
- **DoD:** Tests grün; `python manage.py export_promptfoo_configs --check` → Exit 0.

#### D2.3 — `.gitignore` + Doku (developer)

- `.gitignore`: `promptfoo/generated/`, `promptfoo/results*.json`, `promptfoo/node_modules/`
  (`.gitignore`-Queue Index §d.2: nur eigene Zeilen).
- `docs/superpowers/specs/2026-08-16-prompt-variable-catalog-design.md` §6 Nachtrag (echo statt Mock,
  kein `--fail-on-error`, Templating aus); `docs/superpowers/specs/index.md:91` Phase 3 → „umgesetzt in PR …".
- Kurzabschnitt „Prompt-Regressionsnetz" in `README.md` „Running Tests" (Befehle aus D2.4).

#### D2.4 — CI-Job `prompt-regression` (devops-engineer)

- **Ändern `.github/workflows/ci.yml`:** neuer Job (läuft immer, kein Pfadfilter — ein pfadgefilterter
  Required-Check bliebe „pending"):
  - `services`: `postgres` (`pgvector/pgvector:pg16`, wie `backend-test`); kein Redis nötig
    (Memory wird in Fällen explizit übergeben, sonst fail-open).
  - **Lieferkette und Rechte (QR-S12, KA-D-04):** Job-Block `permissions: {contents: read}`;
    `actions/checkout` mit `persist-credentials: false`; **keine `secrets.*`** im Job — der Fernet-Testschlüssel
    für `FIELD_ENCRYPTION_KEY` wird im Job erzeugt (`python -c "from cryptography.fernet import Fernet;
    print(Fernet.generate_key().decode())"`, per `::add-mask::` maskiert, nach `$GITHUB_ENV`).
    **Neu `promptfoo/package.json` + `promptfoo/package-lock.json`** pinnen `promptfoo` exakt auf `0.124.1`
    (Lock mit `integrity`); Installation `npm ci --ignore-scripts --prefix promptfoo`; Aufruf über
    `promptfoo/node_modules/.bin/promptfoo` — **kein** `npx --yes`.
  - Steps: checkout · setup-python 3.12 + pip-Cache (wie `:97-112`) · `pip install -r backend/requirements.txt`
    · Fernet-Testschlüssel erzeugen · `cd backend && python manage.py migrate --noinput` (DB-Env wie `:131-152`,
    **ohne** die `secrets.*`-Zeilen; `DJANGO_SETTINGS_MODULE=reqogniloom.settings_test`)
    · `python manage.py export_promptfoo_configs --check` · `python manage.py export_promptfoo_configs --out ../promptfoo/generated`
    · setup-node `22` · `npm ci --ignore-scripts --prefix promptfoo`
    · `promptfoo/node_modules/.bin/promptfoo eval -c promptfoo/generated/*.promptfooconfig.yaml --no-cache --no-share -o promptfoo/results.json`
    mit `env: PROMPTFOO_DISABLE_TEMPLATING: "true"` (RB-D10), `PROMPTFOO_DISABLE_TELEMETRY: "1"`,
    `PROMPTFOO_DISABLE_UPDATE: "1"` · `actions/upload-artifact` (SHA-gepinnt wie übrige Actions) für
    `promptfoo/generated` + `results.json`, `if: always()`. `timeout-minutes: 20`.
  - Kein `--fail-on-error` (existiert nicht, RB-D07); Promptfoo beendet mit **100** bei einem
    fehlgeschlagenen Test, 1 bei Fehlern → Job rot.
  - Provider `echo` (vorläufig, ENT-D8 = A; bei ENT-D8 = B nur der Provider-Eintrag des Exporters geändert).
- **TDD (Workflow-Vertrag, QR-S12):** neu `scripts/test_prompt_regression_workflow.py` (`yaml.safe_load` auf
  `.github/workflows/ci.yml`): Job `prompt-regression` existiert ohne `paths`-Filter, enthält im Text kein
  `secrets.`, hat `permissions == {"contents": "read"}`, Checkout mit `persist-credentials: false`, kein
  `npx`-Aufruf, `npm ci` mit `--ignore-scripts`. **CI-Anbindung im selben PR:** Job `agent-templates-test`
  (`ci.yml:265`) ruft `pytest docs/agent-templates dist scripts/test_prompt_regression_workflow.py` (RB-D18).
- **DoD:** Job grün im PR; Workflow-Vertragstest grün in `agent-templates-test`; **Negativnachweis** im PR-Text:
  ein Commit mit absichtlich falscher Assertion (`not-contains` auf einen vorhandenen Satz) → Job-Log
  `exit code 100`; Commit danach revertiert (Nachweis = Link auf den roten Lauf, Index §b G4).

#### D2.5 — Required Check + Übergabe an Plan A (user, Gate)

- Nutzer trägt `prompt-regression` in die Branch-Protection von `main` ein (GitHub-Einstellung, keine
  Agentenaufgabe). **DoD:** `gh api repos/Popoboxxo/ReqogniLoom/branches/main/protection/required_status_checks --jq '.contexts'`
  enthält `prompt-regression` (bzw. Job-Namen laut Workflow). Nutzer-Gate **U-1** der Entscheidungsliste §6.
  Damit ist das Promptfoo-Gate G1–G4 (Index §b, (xiii) P1) vollständig; Plan A P2-Eintritt verweist wörtlich darauf.

#### D2.6 — `secret-scan` deckt Env-Geheimnisse ab (devops-engineer, Review security-auditor; Welle 0)

- **Anlass:** QR-S03 (hoch), Index §h Punkt 5. `secret-scan` prüft heute nur die Regel `reqlo-api-key`
  (`ci.yml:463,466`, `.gitleaks.toml`); Env-Geheimnisse (`SECRET_KEY`, `AUTH_JWT_SECRET`, …) fallen durch.
- **Eintritt:** Sofortmaßnahme Index §h ausgeführt (Backups außerhalb des Repos); ENT-X1 entschieden
  (Rotation ja/nein — beeinflusst nicht den Code dieser Task, aber den Start jedes Agentenlaufs mit `git add`).
- **Ändern `.gitleaks.toml`:** neue Regel `env-secret-assignment` mit
  `regex = '''(?m)^(SECRET_KEY|AUTH_JWT_SECRET|FIELD_ENCRYPTION_KEY|[A-Z_]*API_KEY|[A-Z_]*PASSWORD)=\S{12,}'''`;
  Regel-Allowlist (Pfade): `\.example$`, `(^|/)tests?/`, `(^|/)test_[^/]*\.py$`, `^e2e/`; Stopwords
  `CHANGE-ME`, `change-me` (Platzhalter in Doku). Kopfkommentar
  der Datei um den zweiten Gate-Zweck ergänzen.
- **Ändern `.github/workflows/ci.yml` Job `secret-scan`** (`:436-466`): dritter, **blockierender** Schritt
  „Scan PR diff for env secrets": `gitleaks git . --config .gitleaks.toml --enable-rule env-secret-assignment
  --log-opts="<base>..HEAD" --redact --exit-code 1`; `<base>` = `origin/${{ github.base_ref }}` bei
  `pull_request`, `${{ github.event.before }}` bei `push` (Null-SHA beim ersten Push → nur `HEAD`).
  Nur der Diff, damit historische Testwerte nicht anschlagen. Die bestehenden zwei Schritte bleiben unverändert.
- **Ändern `.gitignore`** (Zeilen `:18-20`): `.env.bak*` ergänzen (bzw. `.env*` mit `!.env.example` — wirkt
  ohne Schrägstrich auf allen Ebenen, deckt `frontend/.env.example`; hat die Sofortmaßnahme das schon gesetzt,
  nur Test). `.gitignore`-Queue Index §d.2.
- **Neu `scripts/test_gitignore_env.py`** (pytest, `subprocess`): `git check-ignore -q .env.bak-x` → Exit 0
  (ignoriert); `.env.example` → **nicht** ignoriert; `.env` → ignoriert. **CI-Anbindung im selben PR:**
  Job `agent-templates-test` ergänzt `scripts/test_gitignore_env.py` im pytest-Aufruf (RB-D18).
- **TDD:** zuerst `scripts/test_gitignore_env.py` rot gegen `b175c970` (`.env.bak-x` nicht ignoriert).
- **Negativnachweis (im PR):** ein Commit mit Datei `deploy/tmp-leak.env` und Dummy-Zeile
  `SECRET_KEY=dummy-not-a-real-secret-123456` → neuer Schritt rot; Commit danach revertiert; PR per
  Squash-Merge, damit der Dummy-Commit nicht in `main` landet. **Nie** einen echten Wert verwenden.
- **DoD:** `secret-scan` grün nach Revert; Negativlauf verlinkt; `agent-templates-test` grün;
  Planhinweis in allen Plänen („`secret-scan` deckt nur `reqlo_`-Keys") gilt ab Merge als erledigt
  (KA-ALL-09).

### WP D3 — #792 neu schreiben, Offenes umsetzen (Welle 4)

#### D3.1 — RFC neu fassen (documenter; Ausführung `gh issue edit` durch orchestrator-geführten Lauf)

- Neuer Issue-Body = Tabelle aus (iii) D3 mit Spalten Punkt/Status/Beleg, Abschnitt „Decided against —
  do not reimplement" (1, 2, 4-Weg, 14, 15, 16-Weg), „Offen" (7, 12, 13, 18) mit Verweis auf D3.2–D3.4;
  Label `critical` entfernen (Nutzerbestätigung, da Label-Änderung). **DoD:** Issue-Body enthält 18 Zeilen.

#### D3.2 — `scripts/setup.sh` mit Port-Vorprüfung (#7, #12) (devops-engineer)

- **Neu `scripts/setup.sh [--env-file PATH] [--check-ports]`:** existiert die Env-Datei nicht, Kopie aus
  `.env.example`; ersetzt **nur** Werte, die mit `CHANGE-ME` beginnen: `SECRET_KEY`, `AUTH_JWT_SECRET`
  (`openssl rand -hex 50`), `DB_PASSWORD`, `DB_APP_PASSWORD`, `SYSTEM_ADMIN_PASSWORD`
  (`openssl rand -base64 32 | tr -d '/+='`), `FIELD_ENCRYPTION_KEY` (Fernet:
  `openssl rand -base64 32 | tr '+/' '-_'`); existierende Werte bleiben (idempotent), Datei `chmod 600`,
  Ausgabe nennt Schlüssel, nie Werte. `--check-ports`: liest `BACKEND_PORT` (Default 8001),
  `FRONTEND_PORT` (5173) aus der Env-Datei, prüft `bash -c ':>/dev/tcp/127.0.0.1/<port>'`; belegt →
  `Port <p> is already in use — set BACKEND_PORT/FRONTEND_PORT in .env`, Exit 2.
  Kein DB-Init (obsolet, siehe Tabelle Pkt. 7).
  **Backups (QR-S03, KA-D-03):** muss das Skript eine bestehende Env-Datei sichern, dann **nur außerhalb des
  Repo-Baums** (`${XDG_STATE_HOME:-$HOME/.local/state}/reqogniloom/env-backups/<zeitstempel>.env`, Rechte
  `600`); es legt nie `.env.bak*` o. ä. im Repo an. Liegt die Ziel-Env-Datei innerhalb des Repos, prüft das
  Skript nach dem Schreiben `git check-ignore -q <datei>` und bricht sonst mit Exit 3 ab.
- **TDD:** `scripts/test_setup_script.py` (pytest, `subprocess`, tmp-Dir): erzeugt Datei; zweiter Lauf
  ändert nichts; `FIELD_ENCRYPTION_KEY` ist gültiger Fernet-Key (`cryptography.fernet.Fernet(key)`);
  belegter Port (Test öffnet Socket) → Exit 2; `test_backup_lands_outside_repo` (`XDG_STATE_HOME` auf
  tmp-Dir gesetzt; danach keine `.env.bak*`/`*.env`-Datei im Repo-Arbeitsbaum, Backup im State-Dir mit
  Modus `0o600`). CI: `agent-templates-test` (`ci.yml:265`) Befehl erweitert um
  `scripts/test_setup_script.py` + `pip install cryptography` (RB-D18: nur diese Datei, nicht ganz `scripts/`,
  da die übrigen `scripts/test_*.py` heute in keinem Job laufen; Rebase auf P1-3/P1-4, die denselben
  Befehl erweitern).
- **DoD:** Tests grün; `README.md` „How to Start" verweist auf `bash scripts/setup.sh --check-ports`.

#### D3.3 — `make wipe` mit Pflicht-Backup (#13) (devops-engineer)

- **Ändern `Makefile`:** Ziel `wipe` (`CONFIRM=yes` Pflicht, sonst Abbruch mit Hinweis):
  1. `$(COMPOSE) -f deploy/docker-compose.yml -f deploy/docker-compose.offhost.yml --project-directory . run --rm -e BACKUP_ONCE=true -e BACKUP_INITIAL_DELAY=0 postgres-backup`
     (verlangt `BACKUP_OFFHOST_DIR`; ohne → Compose-Fehler `BACKUP_OFFHOST_DIR must be set`, Abbruch),
  2. **Backup-Prüfung (QR-S22, KA-D-09):** neu `deploy/check-offhost-backup.sh "$BACKUP_OFFHOST_DIR"` — die
     neueste Datei `reqogniloom_*.sql.gz` (Namensschema `deploy/docker-compose.yml:328`) muss jünger als 5 min
     sein, > 0 Byte, `gzip -t` ok, und `zcat <datei> | head -n 5` enthält `PostgreSQL database dump`; sonst
     Exit 1 mit Grund. Exit 0 des Backup-Laufs allein genügt **nicht**.
  3. nur wenn Schritt 1 **und** 2 Exit 0: `… --profile honcho --profile qdrant --profile bluepencil down -v`.
  Begründung: `down -v` löscht auch `postgres_backup_data` — nur die Off-host-Kopie überlebt.
- **Ändern `deploy/README.md:300-310`:** destruktiver Block verweist auf `make wipe CONFIRM=yes`.
- **Test (CI-angebunden):** neu `scripts/test_offhost_backup_check.py` (pytest, `subprocess`, tmp-Dir, ohne
  Docker): leere Datei → Exit ≠ 0; Datei älter als 5 min (`os.utime`) → Exit ≠ 0; kaputtes gzip → Exit ≠ 0;
  gültiges gzip mit `-- PostgreSQL database dump`-Kopf → Exit 0; leeres Verzeichnis → Exit ≠ 0.
  **CI-Anbindung im selben PR:** `agent-templates-test` ruft zusätzlich `scripts/test_offhost_backup_check.py`
  (RB-D18). Zusätzlich `make -n wipe CONFIRM=yes` im PR protokolliert (Backup-Befehl und Prüfskript vor
  `down -v`). **DoD:** Test grün in `agent-templates-test`; `make wipe` ohne `CONFIRM` → Exit ≠ 0, nichts
  gelöscht.

#### D3.4 — Dev-Overlay sichtbar machen (#792 Pkt. 18) (developer)

- **Eintritt:** Compose-Queue Index §d.2 (QR-T20): A PR-A2 → D P2-1 → G PR 13 → **D P3-4**; P3-4 rebased auf
  G PR 13. Fassung = vorläufig, ENT-D7 = A.

- **Ändern `backend/reqogniloom/health.py:299` `_collect_advisory`:** `advisory["django_env"] = settings.DJANGO_ENV`
  (kein Eintrag in `warnings` → Status bleibt `ok`, E2E/Monitoring unberührt); README-Hinweis:
  `curl -s localhost:8001/health/ | jq .advisory.django_env` ≠ `production` = Dev-Overlay aktiv.
- **Ändern `deploy/docker-compose.yml:1,33-42`:** Kopf „ReqFlow" → „ReqogniLoom"; Override-Hinweis
  korrigiert (Datei liegt in `deploy/`, wird nur bei Aufruf ohne `-f` aus `deploy/` automatisch gemergt;
  Produktion immer mit explizitem `-f`).
- **TDD:** `backend/reqogniloom/tests/test_health_django_env_advisory.py` — `override_settings(DJANGO_ENV="development")`
  → `advisory.django_env == "development"`, `status` unverändert. **DoD:** grün in `set-2-api`.
  (Option „Override umbenennen" siehe ENT-D7.)

### WP D4 — Client-Doku (#1171) (Welle 4)

Regel: `docs/clients/*.md` sind generiert — Änderungen in `clients/registry.yaml` bzw.
`scripts/clients/render.py`, danach `python3 scripts/clients/render.py`; `--check` muss grün sein.

#### D4.1 — Offene kaputte Anweisungen (documenter + developer)

- K3: `STAGE2*.md` Zeile 23 `python3`; `SHELL_COMMAND_DOCS` (`test_doc_surface_consistency.py:54-58`)
  um `docs/clients/STAGE2.md`, `docs/clients/STAGE2.de.md` erweitern.
- K5: `INSTALL.md:137-142` + `python3 dist/codex/build_codex_package.py`; Satz „each depends on the
  previous step's output" auf die echte Kette prüfen und korrigieren.
- K7/K13: `README.md:428-446` und `:1213-1250` ersetzen durch Verweis auf `docs/clients/` + ein
  verifiziertes Beispiel (Claude Desktop über `npx -y mcp-remote@<x.y.z> "$REQOGNILOOM_MCP_URL/mcp/" --header "X-API-Key:${REQOGNILOOM_API_KEY}"`
  **nur nach** manueller Verifikation durch den Nutzer; sonst nur Verweis). Kein `reqlo_…`-Beispielwert mehr.
  **Versionspin (QR-S18, KA-D-08):** `mcp-remote` nur mit **exakt gepinnter** Version ≥ 0.1.16
  (CVE-2025-6514 betrifft ältere); `<x.y.z>` = beim Implementieren verifizierte Version, im PR genannt.
- K12: `opencode.jsonc` (inkl. `~/.config/opencode/opencode.jsonc`) in `INSTALL.md:52-53,83` und Registry-Text für `opencode.md:72`.
- K14: `clients/registry.yaml` Claude-Fallback → `claude mcp add --transport sse reqogniloom "$REQOGNILOOM_MCP_URL/mcp/sse/" --header "X-API-Key: $REQOGNILOOM_API_KEY"`.
- L14/RB-D21: Antigravity-Verify als ausführbarer Befehl (curl-SSE-Handshake aus `scripts/clients/verify.sh`), Text je Sprache.
- **TDD (zuerst rot):** `docs/agent-templates/test_doc_surface_consistency.py` neue Verbote in
  `README.md`, `INSTALL.md`, `docs/clients/*.md`: `/mcp/stdio/`, `YOUR_API_KEY`, `reqlo_[A-Za-z0-9]{8,}`,
  `opencode\.json(?![.c])`, Zeile mit `--transport http` und `/mcp/sse/`, ungepinntes `mcp-remote`
  (`npx (-y )?mcp-remote(?!@\d)`, QR-S18).
- **DoD:** `pytest docs/agent-templates dist -q` grün; `python3 scripts/clients/render.py --check` OK.

#### D4.2 — Offene Lücken (documenter)

- L2: `INSTALL.md` neuer Abschnitt „Per-client pages" (Codex, Kimi, Hermes → `docs/clients/*`) + „Model / Provider" als Verweis, kein Duplikat.
- L3: `docs/clients/README*.md` (über Registry) Tabelle der Platzhalterformen: `${VAR}` (Claude Code, Antigravity), `{env:VAR}` (OpenCode), `bearer_token_env_var`/`env_http_headers` (Codex), `bearerTokenEnvVar` (Kimi).
- L10: `codex.md` direkter Befehl `codex mcp add reqogniloom --url "$REQOGNILOOM_MCP_URL/mcp/" --bearer-token-env-var REQOGNILOOM_API_KEY` (CLI belegt, D-L17).
- L12: `opencode agent create` nur aufnehmen, wenn `opencode agent create --help` es zeigt (Implementierer prüft; sonst als „nicht unterstützt" streichen).
- RB-D17: `INSTALL.md:166-170` und Docstring `dist/test_mcp_convention_parity.py:23` korrigieren („Codex nutzt Bearer; Header-Variante `env_http_headers` existiert, wird bewusst nicht verwendet").
- **DoD:** `render.py --check` OK; DE/EN-Paare vollständig (bestehender Test in `scripts/clients/test_render.py`).

#### D4.3 — Claude-Plugin: `userConfig` + `plugin validate` in CI (developer, Review code-reviewer)

- **Ändern `dist/plugins/claude-code/build_claude_plugin.py`:** `plugin.json` erhält
  `"userConfig": {"mcp_url": {"type":"string","title":"ReqogniLoom URL","description":"Base URL, e.g. https://reqlo.example.com","required":true}, "api_key": {"type":"string","title":"API key","description":"reqlo_… key","sensitive":true,"required":true}}`;
  `.mcp.json`: `"url": "${user_config.mcp_url}/mcp/sse/"`, `"X-API-Key": "${user_config.api_key}"` (vorläufig, ENT-D4 = A).
- **Ändern `dist/test_mcp_convention_parity.py`:** `${user_config.*}` als zulässige Referenzform für Claude Code.
- **CI `client-artifacts-check.yml`:** Schritt `npm i -g @anthropic-ai/claude-code@2.1.306` (gepinnt) +
  `claude plugin validate --strict dist/plugins/claude-code/reqogniloom` + `claude plugin validate .`.
- **TDD:** `dist/plugins/claude-code/test_build_claude_plugin.py::test_plugin_declares_user_config_and_mcp_uses_it`.
- **DoD:** Tests + Validate grün; `claude-code.md` (Registry) nennt `claude plugin configure reqogniloom`.

### WP D5 — Externe Publikation (#1230)

#### Nutzer-Checkliste (Handarbeit, Gates — keine Agenten-Tasks)

| Gate | Welle | Schritt (Nutzer) | Nachweis (Akzeptanz aus #1230) | schaltet frei |
|---|---|---|---|---|
| U-W1a | W1 | `claude plugin marketplace add Popoboxxo/ReqogniLoom` auf fremdem Gerät, `claude plugin install reqogniloom@reqogniloom-marketplace` | Screenshot/Log „installed" + `claude mcp list` connected | D4 L7-Text „öffentlicher Weg" |
| U-W1b | W1 | Kuratierte Anthropic-Einreichung | erst mit stabilem Release (E4) | – |
| U-W2a | W2 | npm-Konto/Org `popoboxxo`, Scope `@popoboxxo` | `curl -s -o /dev/null -w '%{http_code}' https://registry.npmjs.org/-/org/popoboxxo/package` → 200 | D5.3 |
| U-W2b | W2 | Trusted Publishing (OIDC) für `publish-npm.yml`, Environment `release` | npm-Einstellungsseite (Screenshot) | erster Publish |
| U-W3a | W3 | GitHub-Konto `popoboxxo` als Inhaber von `io.github.popoboxxo` | `mcp-publisher login github-oidc` im Dispatch-Lauf erfolgreich | Publish |
| U-W3b | W3 | Entscheidung `server.json`-Remote (ENT-D6, vorläufig A) | Kommentar im Issue | D5.2 |
| U-W4 | W4 | Codex-Marketplace-Format verifizieren, E5 entscheiden, Antigravity-Store | Install-Beleg je Store | D4 L11 |
| U-W5 | W5 | Hermes-Katalog-Einreichung, Kimi-FR `kimi mcp add`, Aggregatoren (E7) | Links im Issue | – |

#### D5.1 — `mcp-publisher` pinnen (devops-engineer, Review security-auditor)

- `publish-mcp-registry.yml:77-96`: URL `…/releases/download/v1.8.1/mcp-publisher_linux_amd64.tar.gz`,
  danach `echo "a06c9096dcb9727c13555b6be26c7effa707b01f06a4c561ba7a3635443cf2cc  /tmp/mcp-publisher.tar.gz" | sha256sum -c -`;
  TODO-Kommentare Z. 20/77 entfernen. **DoD:** `actionlint` (Job `workflow-lint`) grün; `grep -c latest/download` → 0.

#### D5.2 — `server.json` mit URL-Template (developer; nach U-W3b)

- `scripts/clients/render.py:388`: `"url": "https://{host}/mcp/"` + `"variables": {"host": {"description": "Hostname of your self-hosted ReqogniLoom instance", "isRequired": true}}`.
- **TDD:** `scripts/clients/test_render.py::test_server_json_remote_uses_host_variable` + Validierung gegen
  Schema 2025-12-11 (`mcp-publisher validate` im Dispatch-Lauf). **DoD:** `render.py --check` OK.

#### D5.3 — OpenCode-npm-Paket (developer; erst nach U-W2a)

- **Neu:** `dist/npm/reqogniloom-opencode/` (Builder `dist/opencode/build_opencode_package.py` erweitert:
  `package.json` `@popoboxxo/reqogniloom-opencode`, Version aus `VERSION`, Plugin-Modul registriert MCP
  `remote` + kopiert Skills), Test `dist/opencode/test_build_opencode_package.py::test_npm_package_is_generated_and_versioned`;
  `scripts/check_plugin_packages.py`-Carrier ergänzen.
- **DoD:** `npm pack --dry-run --prefix dist/npm/reqogniloom-opencode` listet `package.json` + Modul;
  Workflow-Dispatch ohne `enable_publish` meldet nicht mehr „DRAFT … does not exist".

### WP D6 — #92 schließen (D6.1, Welle 4), #89 absichern (D6.2, **Welle 3** vor Plan E E3.8)

Planbasis führt D6 als „Rest" ohne eigene Welle; Index §b legt D6.2 (PR P3-1) in Welle 3 vor Plan E P3-5
(E3.8), weil beide `seed_demo.py`/`test_seed_demo.py` ändern (QR-T19). D6.1 bleibt Welle 4.

#### D6.1 — #92 verifizieren und schließen (tester → orchestrator)

- Nachweis-Lauf: `pytest rest_api/tests/test_sec02_sec03_workspace_fence.py mcp_server/tests/test_mcp_workspace_fence_1376.py -q`
  → 0 failed (CI-Beleg genügt). Abschlusskommentar: Pkt. 1 = Fence `workspace_ids` (ADR-011 SEC-03,
  REST+MCP, D-L14), Pkt. 2/3 = IdChip/`McpConnectionSection`; UI-Lücke → Folge-Issue an Plan E
  (vorläufig, ENT-D5 = A).
- **DoD:** #92 geschlossen, Folge-Issue verlinkt.

#### D6.2 — `seed_demo` gegen Produktionsbetrieb absichern (developer, Review security-auditor; Welle 3)

- **Eintritt:** Welle 3 (Index §b); vor Plan E P3-5 (E3.8) — Merge-Queue `seed_demo.py` **D P3-1 → E P3-5**
  (Index §d.2). Fassung = **vorläufig, ENT-D9 = B** (Empfehlung Sicherheitsreview QR-S15). Ohne Entscheidung
  gilt laut Entscheidungsliste Option A (nur `DEBUG=False` sperrt) als Untergrenze; Variante A am Ende der Task.
- **Ändern `backend/auth_tenancy/management/commands/seed_demo.py`:**
  - Das eingebaute Default-Passwort gibt es **nur** mit explizitem Opt-in
    `SEED_DEMO_ALLOW_DEFAULT_PASSWORD=1` — **unabhängig von `DEBUG`** (Dev-Overlay setzt `DEBUG=True` und kann
    produktionsnah versehentlich aktiv sein). Ohne Opt-in und ohne `SYSTEM_ADMIN_PASSWORD`/`DEMO_ADMIN_PASSWORD`
    → `CommandError("seed_demo refuses the built-in demo password; set SYSTEM_ADMIN_PASSWORD or SEED_DEMO_ALLOW_DEFAULT_PASSWORD=1 (test only).")`.
    Damit ist die Planbasis-Forderung „gegen `DEBUG=False` absichern" mit erfüllt. QS mit gesetzter Variable
    läuft weiter — CLAUDE.md-Regel „migrate dann seed_demo" bleibt erfüllt.
  - `--reset-password` auf das Default-Passwort nur mit Opt-in (gleiche Meldung).
  - Login-Hinweis (`:123-126`) druckt das Passwort nur, wenn das Default-Passwort per Opt-in genutzt wurde;
    sonst „password from SYSTEM_ADMIN_PASSWORD" (nie ein gesetzter Wert im Log).
  - Docstring `:4-7`: `bootstrap`-Service → `application.self_init` im `migrate`-Service.
- **CI/Test-Umgebungen im selben PR prüfen:** `.github/workflows/playwright.yml` ruft `seed_demo` im Step
  „Run Django migrations" (`:74-115`) mit gesetztem `SYSTEM_ADMIN_PASSWORD` (`:112`) — dort greift der
  Env-Zweig, das Opt-in ist **nicht nötig** und wird nicht gesetzt (Abweichung zu KA-D-06 „CI setzt die
  Variable", da kein Default-Passwort genutzt wird; der grüne `e2e`-Lauf belegt es). (Einziger automatischer Aufrufer;
  `testing/docker-compose.test.yml` und `deploy/docker-compose.override.yml` rufen `seed_demo` nicht auf,
  geprüft per `grep -n seed_demo`). Manueller Dev-Aufruf (CLAUDE.md „migrate dann seed_demo") läuft mit
  gesetztem `SYSTEM_ADMIN_PASSWORD` aus `.env` weiter; ohne Passwort-Variable braucht er das Opt-in
  (Release-Note). Prod-Compose (`deploy/docker-compose.yml`) setzt die Variable **nie** (Contract-Test unten).
- **Ändern `README.md:281-293`** („creates demo artifacts" → „provisions demo tenant/workspace/admin, idempotent"),
  `:803-806` Prod-Hinweis „nur mit gesetztem `SYSTEM_ADMIN_PASSWORD`"; `.env.example` dokumentiert die
  Opt-in-Variable als „test only".
- **TDD:** `backend/auth_tenancy/tests/test_seed_demo.py` neue Fälle:
  `test_default_password_requires_explicit_opt_in_even_with_debug` (`override_settings(DEBUG=True)`, ohne Opt-in
  → `CommandError`), `test_refuses_default_password_without_debug`,
  `test_runs_with_env_password_without_opt_in`, `test_does_not_echo_env_password` (`capsys`),
  `test_opt_in_keeps_default_password` (Testpfad mit Opt-in), `test_prod_compose_never_sets_opt_in` (`yaml.safe_load` auf
  `deploy/docker-compose.yml`, Variable in keinem Service).
- **DoD:** Tests grün in `set-2-api`; E2E-Job `e2e` grün (CI setzt `DEBUG=True` + `SYSTEM_ADMIN_PASSWORD`, `playwright.yml:79-115`, ohne Opt-in);
  #89 mit Kommentar schließen (CI nutzt `seed_demo` weiter, Login-Grunddaten kommen aus `self_init`).
- **Variante A (nur falls ENT-D9 = A):** Sperre nur bei `settings.DEBUG is False`; Opt-in-Variable,
  `test_default_password_requires_explicit_opt_in_even_with_debug` und `test_prod_compose_never_sets_opt_in`
  entfallen; `test_debug_keeps_default_password` statt `test_opt_in_keeps_default_password`.

## (v) Abhängigkeiten

**Task → Task:** D1.0 → D1.1 (Template-Umstellung des Smoke-Jobs) → D1.2 (gemeinsames Snippet + Smoke-Job) ·
D1.1 → D1.2 → D1.3 → D1.4 · D2.1 → D2.2 → D2.4 → D2.5 · D2.3 mit D2.2 · D2.4 → D2.6 (`ci.yml`-Queue) →
D1.0 (`ci.yml`-Queue) · D3.1 unabhängig; D3.2 nach D2.6 (gleicher `agent-templates-test`-Befehl), D3.3, D3.4
unabhängig · D4.1 → D4.2 (gleiche Registry-Datei) · D4.3 unabhängig · D5.1 frei; D5.2 nach U-W3b;
D5.3 nach U-W2a · D6.1, D6.2 unabhängig.

**Entscheidungen → Task:** ENT-D8 → D2.2/D2.4 (vorläufig A) · ENT-X1 + Sofortmaßnahme Index §h → D2.6 ·
ENT-D2 (+ Rahmen ENT-C4) → D1.1/D1.2 (**nicht** vorläufig startbar) · ENT-D1, ENT-D3 → D1.1/D1.2 (vorläufig A) ·
ENT-D9 → D6.2 (vorläufig B) · ENT-D4 → D4.3 · ENT-D5 → D6.1 · ENT-D6 → D5.2 · ENT-D7 → D3.4 ·
ENT-X3 → DoD-Ablage (vorläufig C).

**Plan → Plan:**
- **Promptfoo-Gate (Index §b):** Plan A T-A1-1 … T-A1-8 hart nach G1–G4 (D2.4 gemergt **und** D2.5 Required
  Check). Plan A T-A1-8 **erweitert** die D2-Case-Dateien um Szenarien, legt keine neuen an; PR-A9 enthält nur
  auf `main` grüne Szenarien; das `bundle_compression`-Szenario „ohne Memory" wird im selben PR wie T-A1-1
  (PR-A10) scharf geschaltet (QR-T05/T06). Plan B B5-T2 (PR-B15) bringt die Case-Dateien der neuen
  `quality_*`-Slots im **selben PR** mit (QR-T07); D2-Tests und `--check` zählen dynamisch und bleiben grün.
- **Compose-Queue `deploy/docker-compose.yml` (Index §d.2, QR-T20):** A PR-A2 → **D P2-1** → G PR 13 →
  **D P3-4**. P2-1-Eintritt: A PR-A2 gemergt. Plan G G3.3 grept ohne `node:22-slim`-Ausnahme, sobald P2-1
  gemergt ist (D1.1 ersetzt `node:22-slim`).
- **`seed_demo`-Queue (Index §d.2, QR-T19):** **D P3-1 (D6.2, Welle 3) → E P3-5 (E3.8)**; E3.8-Eintritt
  „D P3-1 gemergt".
- **`ci.yml`-Queue (Index §d.2):** D P1-3 → D P1-4 → D P1-1 (Welle 0); D P2-2 (Welle 2); D P3-2 (Welle 4).
- Plan G #1406 R2-09 → D1.4. Plan E E1 besitzt Key-Fence; Folge-Issue aus ENT-D5 an Plan E.
- `secret-scan`-Abdeckung aller Pläne (KA-ALL-09) hängt an D2.6 (PR P1-4).

## (vi) Rollout, Feature-Flags, Fallback

| Bereich | Schalter | Verhalten bei nicht verfügbarer Komponente |
|---|---|---|
| D1.0 Header | keiner; Rollback = Revert | CSP-Verletzung im Browser → **Revert**; `script-src` wird nie aufgeweicht (Gate im Skript, QR-S17); nur nicht-skriptbezogene Quelle mit Begründung ergänzbar; Gate = Konsole auf 5 Routen |
| D1.1 Hub | Profil `bluepencil` (unverändert), `BLUEPENCIL_HUB_IMAGE`, `BLUEPENCIL_AUTH_SECRET` (Pflicht, vorläufig ENT-D2 = B) | Image nicht ziehbar/arm64 → Hub startet nicht, Loader-Probe scheitert → Layer wird **nicht** installiert, App unberührt (`loader.ts:263-311`); Secret fehlt → `compose up` bricht ab (`:?`); Header leer/falsch → Hub 401 (fail-closed); keine Sitzung → nginx 401 |
| D2.6 Secret-Scan | keiner; Rollback = Revert | Fehlalarm im Diff-Scan → Allowlist-Pfad/Stopword im PR ergänzen (Review `security-auditor`), nie die Regel abschalten |
| D1.2 Layer | Overlay `docker-compose.bluepencil.yml` + Build-Flag | Mount-Quelle fehlt → `compose up` bricht ab (`create_host_path: false`); Dateien fehlen/falscher Hash → Frontend `unhealthy`, Layer-Pfade 404; ohne Overlay: kein Layer (gewollt, Flag im GHCR-Image aus) |
| D2 | Job `prompt-regression` | Promptfoo/npm nicht erreichbar → Job rot (kein Skip); `--check` läuft ohne Node |
| D3.3 | `CONFIRM=yes`, `BACKUP_OFFHOST_DIR` | Backup scheitert **oder** Backup-Datei leer/alt/kaputt/ohne Dump-Kopf (`check-offhost-backup.sh`) → kein `down -v` |
| D3.4 | – | rein informativ |
| D4.3 | – | Nutzer mit Env-Variablen: nach Update `claude plugin configure reqogniloom` (Release-Note, Breaking) |
| D5 | `enable_publish` (bestehend) | ohne Gate kein Publish |
| D6.2 (Welle 3) | `SEED_DEMO_ALLOW_DEFAULT_PASSWORD` (nur Test/CI, vorläufig ENT-D9 = B) / `SYSTEM_ADMIN_PASSWORD` | ohne Opt-in und ohne Passwort-Variable → klare Fehlermeldung statt Default-Passwort, auch bei `DEBUG=True`; Rollback = Revert |

## (vii) Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Image-Tausch bricht Layer (401/Basis/Store/UID) | D1.1 Env-Konfiguration (Basis, Store, Name), Secret + nginx-Header-Injektion, Volume-Init; Contract-Test |
| Unauthentifizierte, mandantenlose Notiz-API inkl. Hub-MCP am Frontend-Port (QR-S02, hoch) | D1.1 vorläufig ENT-D2 = B: Hub-Secret, nginx `auth_request` gegen `/api/v1/auth/me/`, kein Host-Port, Smoke 401/200; Sandbox-Port entfernen; bei A′ schriftliche Risikoakzeptanz + QS-only |
| Env-Geheimnisse (`.env.bak*`) gelangen per `git add -A` ins öffentliche Repo, `secret-scan` bleibt grün (QR-S03, hoch) | Sofortmaßnahme Index §h; D2.6 Diff-Scan + `.gitignore` + Test; bis Merge P1-4: nur explizite Pfade bei `git add` |
| Backup mit Exit 0, aber leer/abgeschnitten → `down -v` vernichtet Daten (QR-S22) | D3.3 `check-offhost-backup.sh` (Alter, Größe, `gzip -t`, Dump-Kopf) |
| `seed_demo` setzt Default-Passwort bei versehentlich aktivem Dev-Overlay (QR-S15) | D6.2 Opt-in unabhängig von DEBUG (vorläufig ENT-D9 = B) |
| Ungepinntes `npx mcp-remote` (CVE-2025-6514) in Doku-Beispielen (QR-S18) | D4.1 exakter Pin ≥ 0.1.16 + Verbot im Konsistenztest |
| Notizverlust beim Hub-Wechsel | gleicher Store-Pfad; QS-Zählung vor/nach (D1.1 DoD) |
| Browser führt veraltetes `attach.js` aus (immutable Cache) | D1.2 `no-cache`-Location; erster Rollout: Nutzer einmal Hard-Reload (Release-Note) |
| QS verliert seine (ungeklärten) Layer-Bytes | Lock = Release v0.5.0; QS-Gate `bp-attach-ready` |
| CSP gilt erstmals fürs Dokument und blockiert Funktionen | QS-Konsolen-Gate; kein Inline-Script im Build (geprüft: 1 `<script src>`) |
| Promptfoo-Feldnamen weichen ab | Pin 0.124.1; Exporter-Test + erster CI-Lauf |
| Promptfoo-Lieferkette (npm, QR-S12) | `promptfoo/package.json` + `package-lock.json` (exakt 0.124.1, Integrity), `npm ci --ignore-scripts`, Job `permissions: {contents: read}`, `persist-credentials: false`, keine `secrets.*` (Fernet-Testschlüssel im Job erzeugt), `--deep` bei `CI` technisch gesperrt; Workflow-Vertragstest |
| Slot-Zahl ändert sich (Plan B: neue `quality_*`-Slots) → Required Check rot | Soll-Zahl dynamisch `len(get_prompt_slots())`; neuer Slot bringt Case-Datei im selben PR (Index §b) |
| Export rendert mit Tenant-Zeilen statt Defaults | Nil-Tenant; Test prüft Factory-Body-Gleichheit |
| `seed_demo`-Guard bricht QS-/CI-Routine | Guard greift nur ohne gesetztes Passwort und ohne Opt-in; CI setzt `SYSTEM_ADMIN_PASSWORD` bereits (`playwright.yml:112`); Release-Note für manuelle Dev-Aufrufe ohne Passwort |
| `userConfig` bricht Env-Installationen | Release-Note + ENT-D4 |
| `make wipe` mit fehlendem Off-host-Pfad | Compose `:?`-Fehler bricht vor `down -v` ab |

## (viii) Aufwand je WP (grob)

| WP | Aufwand | Annahmen |
|---|---|---|
| D1.0 | 0,5 PT | Snippet + Smoke-Job |
| D1.1–D1.4 | 3,5–4 PT | Hub 1, Zugriffsschutz (Secret, nginx-Template, `auth_request`; vorläufig ENT-D2 = B) 0,5–1, Layer/Fetch/nginx/Overlay 1,5, Doku 0,5 |
| D2.1–D2.5 | 3–4 PT | Fall-Dateien je Registry-Slot (am Messstand 23) ≈ 1 PT; CI-Einrichtung inkl. Lockfile/Rechte 0,5 PT |
| D2.6 | 0,5 PT | gitleaks-Regel, Diff-Schritt, `.gitignore`-Test, Negativnachweis |
| D3 | 2 PT | 3.1 0,25 · 3.2 0,75 (inkl. Backup außerhalb Repo) · 3.3 0,75 (inkl. Backup-Prüfskript + Test) · 3.4 0,25 |
| D4 | 2,5 PT | 4.1 0,75 · 4.2 1 · 4.3 0,75 |
| D5 (Agent) | 0,5 PT + 1,5–2 PT (D5.3) | Nutzerzeit nicht geschätzt |
| D6 | 1 PT | D6.1 0,25 (Welle 4) · D6.2 0,75 inkl. Opt-in + Contract-Test (Welle 3) |

Schätzungen des Plan-Autors; Schärfung durch `effort-estimator` (Planbasis O5).

## (ix) Entscheidung nötig

IDs laut [Entscheidungsliste](2026-10-21-entscheidungen-offen.md) (früher `D-D1` … `D-D8`). Spalte
„Plan-Fassung" = was dieser Plan bis zur Entscheidung umsetzt („vorläufig") bzw. ob die Task wartet.

| ID | Frage | Optionen | Empfehlung | Plan-Fassung | blockiert |
|---|---|---|---|---|---|
| ENT-D1 | Hub-/Layer-Version | A) 0.5.0 (QS-geprüft) · B) 0.8.0 (aktuell `hub`/`latest`) | **A**; 0.8.0 als eigener Lock-Bump danach | vorläufig A | P2-1, P2-2 |
| ENT-D2 ⚠ | Hub-Auth (Konflikt Plan ↔ QR-S02) | A) Entrypoint umgehen, keine Auth, kein Host-Port · B) Image-Secret + nginx injiziert `x-bluepencil-auth` + `auth_request` gegen Session-Check · C) wie A, Hub-MCP nur über separaten Port mit Secret · A′) wie A mit schriftlicher Risikoakzeptanz, Profil nur QS, Sandbox-Port entfernt | **B** (Sicherheitsreview; frühere Planempfehlung A zurückgezogen); A′ nur mit dokumentierter Akzeptanz | D1.1 als **vorläufig B** ausgeschrieben, Variante A′ beschrieben; **Start erst nach Entscheidung** („Vorläufig: nein") | P2-1, P2-2 |
| ENT-D3 | Lock-Bytes | A) Release v0.5.0 · B) QS-Bytes (Herkunft unklar) | **A** | vorläufig A | P2-2 |
| ENT-D4 | Claude-Plugin-Konfiguration | A) `userConfig` (Breaking für Env-Nutzer) · B) Env behalten, nur dokumentieren | **A** | vorläufig A | P3-7 |
| ENT-D5 ⚠ | #92-UI-Lücke | A) schließen + Folge-Issue (Plan E) · B) vor Schließen Workspace-/Scope-Auswahl in `ApiKeysSection` | **A** | vorläufig A | D6.1 |
| ENT-D6 | `server.json`-Remote | A) URL-Template `{host}` · B) Remote weglassen bis gehostete Instanz · C) feste URL (existiert nicht) | **A** | vorläufig A (nach U-W3b) | P3-9 |
| ENT-D7 | #792 Pkt. 18 | A) Health-Advisory + Doku (D3.4) · B) Override in `docker-compose.dev.yml` umbenennen (bricht Doku/CLAUDE.md-Befehle) | **A** | vorläufig A | P3-4 |
| ENT-D8 ⚠ | „Mock-Provider" | A) Promptfoo `echo` (Render-Regression, LLM-frei) · B) eigener Python-Provider über `llm_adapter` (Mock liefert feste Antwort → prüft nichts) | **A** | vorläufig A | D2.2, D2.4, Promptfoo-Gate |
| ENT-D9 ⚠ (neu) | `seed_demo`-Default-Passwort: DEBUG-Bindung vs. Opt-in (QR-S15) | A) wie Planbasis (nur `DEBUG=False` sperrt) · B) Opt-in `SEED_DEMO_ALLOW_DEFAULT_PASSWORD=1` zusätzlich, unabhängig von DEBUG | **B** (erfüllt Planbasis mit) | vorläufig B (Variante A in D6.2 beschrieben) | P3-1 |

Plan-übergreifend relevant: **ENT-C4** (BluePencil in Produktion? vorläufig A „QS-only" — Rahmen für ENT-D2),
**ENT-X1** (Schlüsselrotation; Sofortmaßnahme Index §h vor Welle 0, Eintritt D2.6), **ENT-X3** (Belege
versionieren; vorläufig C — Nachweise im PR-Text/CI-Artefakt), **ENT-V1** (kein Vorziehen ohne Freigabe;
D6.2 in Welle 3 ist Index-Festlegung, kein Vorziehen auf eigene Faust).

## (x) Review-Befunde

| ID | Schwere | Beleg | Auswirkung | Korrigiert in |
|---|---|---|---|---|
| RB-D01 | kritisch | D-L8; `raw/hub-entrypoint-0.5.0.sh`; `host.ts:52-62` | 1:1-Image-Tausch: Auth-Secret → 401, falsche Basis, anderer Store, root-eigener Store unbeschreibbar → Layer still aus, Notizen „weg" | D1.1 |
| RB-D02 | hoch | D-L5; `nginx.conf:136-147` | SPA ohne CSP/XFO/nosniff (Clickjacking, #155-Regression) | D1.0 |
| RB-D03 | hoch | D-L9 | QS-Layer nicht reproduzierbar aus Upstream | D1.2, ENT-D3 |
| RB-D04 | hoch | D-L4; `nginx.conf:144-147` | Layer-Update erreicht Browser bis zu 1 Jahr nicht; Integritätsprüfung lädt frische Bytes, ausgeführt werden alte | D1.2 |
| RB-D05 | mittel | `nginx.conf:131-133,144-147` | Fehlender Mount: `.js` 404, `latest.json` 200 HTML; Bind auf fehlenden Pfad erzeugt leeres Verzeichnis | D1.2 |
| RB-D06 | mittel | D-L8 | Hub-Image nur amd64 | D1.1 (.env-Hinweis), (vi) |
| RB-D07 | mittel | promptfoo-CLI-Doku | `--fail-on-error` aus #587/Spec existiert nicht | D2.4 |
| RB-D08 | mittel | `providers.py:415-470` | Projekt-Mock prüft keinen Prompt | D2.2/D2.4, ENT-D8 |
| RB-D09 | mittel | Spec §6 Beispiel | `llm-rubric` braucht Grader-LLM | D2.1 (`deep_assert`) |
| RB-D10 | mittel | promptfoo-Doku | Nunjucks templatet gerenderte Prompts erneut | D2.4 |
| RB-D11 | mittel | D-L10; `prompt_slots.py:38-45` | 23 statt ~19 Slots; 8 nur geparst | D2.1 |
| RB-D12 | mittel | `prompt_resolver.py:97-183` | Export braucht DB | D2.2, D2.4 |
| RB-D13 | mittel | `seed_demo.py:41,73-78,123-126`; `README.md:281-293` | Default-Passwort in Prod möglich, Passwort im Log, falsche Doku | D6.2 |
| RB-D14 | mittel | D-L15; `README.md:1213-1250` | Beispiele auf 404-Route | D4.1 |
| RB-D15 | mittel | `claude-code.md:33-37` vs. `.mcp.json` | falscher Transport im Fallback | D4.1 |
| RB-D16 | niedrig | D-L6 | ungültige Referrer-Policy | D1.0 |
| RB-D17 | niedrig | `INSTALL.md:166-170`; D-L17 | falsche Codex-Aussage | D4.2 |
| RB-D18 | niedrig | `ci.yml` (kein `scripts/`-Lauf) | `scripts/test_*.py` laufen nirgends | D3.2 (eigener Test aufgenommen; Rest gemeldet) |
| RB-D19 | niedrig | keine Workflow-Treffer | `claude plugin validate` nicht in CI | D4.3 |
| RB-D20 | niedrig | `publish-mcp-registry.yml:92` | ungepinnter Fremd-Binärdownload | D5.1 |
| RB-D21 | niedrig | `antigravity.md:51` | Verify ohne Befehl, deutsch in EN | D4.1 |
| RB-D22 | niedrig | `docker-compose.yml:1,37` | „ReqFlow", irreführender Override-Hinweis | D3.4 |
| RB-D23 | niedrig | `git status` (untracked `frontend/public/bluepencil/{attach.js,…}`) | verwaiste alpha.2-Dateien im QS-Checkout | D1.2 (`.gitignore`) |
| RB-D24 | info | `resource_scope.py:60-80` | Fence heißt SEC-03, nicht CR-03 | D6.1 |

**Querreview-Befunde (Stufe 2)** — Quelle `docs/reviews/PLAN_QUERREVIEW_2026-10-21_{TECHNISCH,SICHERHEIT}.md`:

| ID | Schwere | Auswirkung (kurz) | Korrigiert in |
|---|---|---|---|
| QR-T05 | hoch | Plan A legte D2-Case-Dateien „neu" an | korrigiert in Stufe 2, KA-D-02 → D2.1 (Besitz-/Erweiterungsregel), (v) |
| QR-T06 | hoch | roter Baseline-Case blockiert Required Check | korrigiert in Stufe 2, KA-D-02 → D2.1 („nie roter Case in `main`"), (v) |
| QR-T07 | hoch | Soll-Zahl 23 hart codiert, Plan B `quality_*`-Slots machen Gate rot | korrigiert in Stufe 2, KA-D-01/KA-D-02 → (i) Ziel 2, D2.1, D2.2, (xiii) G1, (viii) |
| QR-T17 | mittel | „grün auf" mit nicht laufenden Checks | korrigiert in Stufe 2, KA-D-12/KA-ALL-06 → (xiii) PR-Tabellen |
| QR-T18 | mittel | Belege gitignored | korrigiert in Stufe 2, KA-ALL-07 → Kopf (vorläufig ENT-X3 = C) |
| QR-T19 | mittel | D6.2 (W4) nach E3.8 (W3) — Wellenwiderspruch | korrigiert in Stufe 2, KA-D-10 → Kopf, WP D6, D6.2, (v), (xii), (xiii) P3-1 |
| QR-T20 | mittel | keine Compose-Merge-Reihenfolge | korrigiert in Stufe 2, KA-D-11 → D1.1, D3.4, (v), (xii), (xiii) P2-1/P3-4 |
| QR-T27 | niedrig | Größenlimit 600 statt Richtwert 400 | korrigiert in Stufe 2, KA-ALL-08 → (xiii) Vorspann |
| QR-S02 | hoch | Hub ohne Auth, Notiz-API/MCP offen am Frontend-Port | korrigiert in Stufe 2, KA-D-05 → D1.1 (vorläufig ENT-D2 = B), (i), (ii), (ix) |
| QR-S03 | hoch | `secret-scan` deckt Env-Geheimnisse nicht ab | korrigiert in Stufe 2, KA-D-03 → neue Task D2.6 / PR P1-4, D3.2; KA-ALL-09 → (xiii) Vorspann |
| QR-S12 | mittel | Promptfoo-Lieferkette, Secrets/Rechte im CI-Job | korrigiert in Stufe 2, KA-D-04 → D2.2, D2.4, (vii) |
| QR-S15 | niedrig | Default-Passwort bei DEBUG=True | korrigiert in Stufe 2, KA-D-06 → D6.2 (vorläufig ENT-D9 = B), (vi) |
| QR-S17 | niedrig | CSP ohne `frame-ancestors`, Aufweichung von `script-src` möglich, Smoke-Image ungepinnt | korrigiert in Stufe 2, KA-D-07 → D1.0, (vi) |
| QR-S18 | niedrig | ungepinntes `npx mcp-remote` (CVE-2025-6514) | korrigiert in Stufe 2, KA-D-08 → D4.1 |
| QR-S22 | niedrig | leeres Backup gibt `down -v` frei | korrigiert in Stufe 2, KA-D-09 → D3.3, (vi) |

## (xi) Widerlegte Annahmen der Planbasis / Issues

1. **#587/Planbasis „~19 Slots":** 23 (D-L10).
2. **#587 „blockiert durch `resolve_and_render`":** existiert (`prompt_resolver.py:259`) — wie Kommentar 27.09.
3. **#587/Spec `--fail-on-error`:** kein Promptfoo-Flag (Exit 100).
4. **Planbasis D2 „Mock-Provider" als Promptfoo-Provider:** Projekt-Mock ignoriert den Prompt → `echo`.
5. **#1418 „QS-Stand = Release 0.5.0":** Bytes weichen ab (D-L9).
6. **#1418 Option B „Image ersetzt `server.js`, Risiko gering":** Image-Defaults (Basis, Store, User, Auth) inkompatibel (RB-D01).
7. **#1418-Kommentar „fehlt der Mount → 200 HTML":** nur für `latest.json`; `.js` → 404.
8. **#1418 Tags `:hub`/`:latest` = 0.5.0:** heute 0.8.0 (D-L8) → nur Digest-Pin trägt.
9. **#1171 „12 kaputte Anweisungen":** 8 behoben (#1293, 2026-10-14), offen K3 (teilweise), K5, K7, K12 + neu K13, K14.
10. **#1171 „`docs/clients/` neu anlegen", „Kimi fehlt", „Hermes-Desktop fehlt":** vorhanden.
11. **#1171 „`codex mcp add --url` ohne Token-Parameter":** `--bearer-token-env-var` vorhanden (D-L17).
12. **#1171/INSTALL „Codex ohne Header-Mechanismus":** `env_http_headers` vorhanden.
13. **#792-Kommentar Zeilenangaben, „1365 Zeilen", Pkt. 17 „nicht verifiziert":** Compose 1610 Zeilen; Pkt. 17 erledigt (D-L13).
14. **Planbasis D3 „4 verworfen, 5 offen":** belegt 6 verworfen (inkl. Weg von 4/16) und 4 offen; keine Neubewertung, nur Beleg.
15. **Planbasis D6 „Workspace-Fence laut CR-03":** Fence = ADR-011 SEC-03; CR-03 = Key-Inventur (`inventory_api_keys.py:1-3`).
16. **#89 offene Frage „ruft CI noch `seed_demo`?":** ja (`playwright.yml:115`), Login kommt aber aus `self_init` (`:107-114`).
17. **#1230 „Platzhalter auf echtes Ziel ersetzen":** kein einzelnes Ziel bei Self-Hosting; Schema erlaubt `{host}`-Template.

## (xii) Parallelisierungs-Matrix

Max. 4 Agenten gleichzeitig **über alle Pläne** (Index §d.1; Host-RAM ~5,8 GiB; Tests nur gezielt, nie
Voll-Suiten parallel). Plan D belegt in Welle 0 einen Slot (D-Strang: P1-2 → P1-3 → P1-4 → P1-1), in Welle 2
den G/D-Slot nach Plan G (P2-1 → P2-2), in Welle 3 einen Slot für P3-1 (vor Plan A A4), in Welle 4 einen Slot
(P3-2 … P3-10). Gleiche Konfliktdatei = Entwicklung parallel, Merge seriell in der Index-Queue (§d.2).

| Task | Voraussetzungen | parallel zu | Konflikt-Dateien (Queue Index §d.2) | Rolle |
|---|---|---|---|---|
| D1.0 | – | D2.1, D2.2, D6.x, D3.x, D4.x, D5.1 | `frontend/nginx.conf`, `frontend/Dockerfile`, `.github/workflows/ci.yml` (neuer Job; Queue P1-3 → P1-4 → **P1-1**) | devops-engineer |
| D1.1 | ENT-D2; D1.0 gemergt; Plan A PR-A2 gemergt | D2.x, D4.x, D6.x | `deploy/docker-compose.yml` (Compose-Queue A PR-A2 → **D P2-1** → G PR 13 → D P3-4), `frontend/nginx.conf`, `frontend/Dockerfile`, `.env.example`, `Makefile` | devops-engineer (Review security-auditor) |
| D1.2 | D1.0, D1.1 | D2.x, D4.x, D6.x | `frontend/nginx.conf`, `ci.yml` (frontend-test), `Makefile`, `.gitignore`, `deploy/verify-frontend-image.sh` | devops-engineer + frontend-component-engineer |
| D1.3 | D1.2 | alle außer D1.2 | Doku-Dateien BluePencil | documenter |
| D1.4 | D1.2 | alle | – (extern) | user / feedback |
| D2.1 | – | D1.0, D1.1, D3–D6 | neu `application/prompt_testing/**` | developer |
| D2.2 | D2.1 | D1.0, D1.1, D3–D6 | neu Command | developer |
| D2.3 | D2.2 | alle außer D1.2 (`.gitignore`) | `.gitignore`, Specs, README | developer |
| D2.4 | D2.2; ENT-D8 (vorläufig A) | D1.1, D3.x, D4.x, D6.x — Merge seriell zu D1.0/D1.2/D2.6/D3.2 (`ci.yml`) | `.github/workflows/ci.yml` (Job + `agent-templates-test`-Befehl), neu `promptfoo/package*.json` | devops-engineer |
| D2.5 | D2.4 gemergt | alle | GitHub-Einstellung (U-1) | user |
| D2.6 | Sofortmaßnahme Index §h; ENT-X1 | D2.1, D2.2, D1.0 (Entwicklung); Merge nach D2.4 | `.github/workflows/ci.yml` (`secret-scan`, `agent-templates-test`), `.gitleaks.toml`, `.gitignore` | devops-engineer (Review security-auditor) |
| D3.1 | – | alle | Issue-Text | documenter |
| D3.2 | D2.6 gemergt (gleicher `agent-templates-test`-Befehl) | alle; Merge seriell zu `ci.yml`-PRs | neu `scripts/setup.sh`, `ci.yml` (agent-templates-test) | devops-engineer |
| D3.3 | – | alle außer D1.1/D1.2 (`Makefile`); Merge seriell zu `ci.yml`-PRs | `Makefile`, `deploy/README.md`, neu `deploy/check-offhost-backup.sh`, `ci.yml` (agent-templates-test) | devops-engineer |
| D3.4 | G PR 13 gemergt (Compose-Queue) | alle außer D1.1 (`docker-compose.yml`) | `backend/reqogniloom/health.py`, `deploy/docker-compose.yml` (Kopf) | developer |
| D4.1 | – | D1.x, D2.x, D3.x, D6.x | `clients/registry.yaml`, `README.md`, `INSTALL.md`, Konsistenztest | documenter + developer |
| D4.2 | D4.1 | wie D4.1 | gleiche Dateien | documenter |
| D4.3 | – | alles außer D5.1 (Workflows) | `dist/plugins/claude-code/**`, `dist/test_mcp_convention_parity.py`, `client-artifacts-check.yml` | developer |
| D5.1 | – | alles außer D4.3 | `publish-mcp-registry.yml` | devops-engineer |
| D5.2 | U-W3b | alles außer D4.1/D4.2 (`render.py`/Registry) | `scripts/clients/render.py`, `server.json` | developer |
| D5.3 | U-W2a | alles außer D4.3 (`dist/`) | `dist/opencode/**`, neu `dist/npm/**` | developer |
| D6.1 | – | alle | Issue | tester |
| D6.2 | Welle 3; ENT-D9 (vorläufig B) | alle außer Plan E E3.8 (Queue **D P3-1 → E P3-5**) | `seed_demo.py`, `test_seed_demo.py`, `README.md`, `.env.example` | developer (Review security-auditor) |

```
Welle 0 (P1):  D2.1 ─▶ D2.2 ─▶ D2.4 ─▶ D2.5 ══▶ Promptfoo-Gate G1–G4 ══▶ Plan A / A1 frei
               D2.2 ─▶ D2.3
               D2.6 (Sofortmaßnahme §h zuerst; ci.yml-Merge nach D2.4)
               D1.0 (ci.yml-Merge nach D2.6)
Welle 2 (P2):  [ENT-D2] ─▶ D1.1 ─▶ D1.2 ─▶ D1.3 ─▶ D1.4   (D1.0 ─▶ D1.1/D1.2; A PR-A2 ─▶ D1.1 ─▶ G PR 13)
Welle 3 (P3-1): D6.2 ─▶ Plan E E3.8
Welle 4 (P3):  D3.1  D3.2  D3.3  D3.4 (nach G PR 13)   D4.1 ─▶ D4.2   D4.3   D5.1   D6.1
Nutzer-Gates:  U-W3b ─▶ D5.2 ;  U-W2a ─▶ D5.3 ;  U-W1a ─▶ D4 (L7-Text) ;  U-1 = D2.5
```

## (xiii) Phasen und PR-Grenzen

**Vorspann (gilt für alle Phasen).**
- **PR-Zuschnitt (Index §f.7, QR-T27):** Richtwert ≤ 400 geänderte Zeilen Produktivcode (ohne Tests,
  Fall-YAML, generierte Dateien, Löschungen), Obergrenze 600 → Split Pflicht; additive und brechende
  Änderungen nie im selben PR (P3-7 `userConfig` ist brechend und steht allein).
- **`secret-scan` (KA-ALL-09, QR-S03):** `secret-scan` prüft bis zum Merge von P1-4 (D2.6, KA-D-03) nur
  `reqlo_`-Keys; Env-Geheimnisse deckt er nicht ab. Kein `git add -A`/`git add .`, nur explizite Pfade.
- **Checks (Index §f.2, KA-ALL-06):** nur reale Jobs. `lint` = ESLint im Frontend (kein Python-Linter);
  `nginx-headers-smoke` und `prompt-regression` entstehen in P1-1 bzw. P1-3 und gelten erst nach deren Merge als
  Check für andere PRs; `client-artifacts` läuft nur bei Pfadtreffer (`clients/**`, `scripts/clients/**`,
  `docs/clients/**`, `dist/**`, `server.json`, `docs/agent-templates/INSTALL.md`, …); kein `build`-/
  `dependency-check`-Job — Backend-Image-Build = lokaler `docker build` durch `devops-engineer`, Log im PR.
- **Belege (KA-ALL-07):** DoD-Nachweise (Negativläufe, QS-Curls, Konsolen-Screens) in PR-Text bzw.
  CI-Artefakt; `docs/test-reports/` ist gitignored (vorläufig, ENT-X3 = C).
- **Branches** von `origin/main` (Index §f.8).

**P1 — Sicherheit + Promptfoo-Netz (Welle 0).**
Eintritt: `origin/main` grün; ENT-D8 entschieden oder vorläufig A; für P1-4 zusätzlich Sofortmaßnahme Index §h
erledigt (ENT-X1). Merge-Reihenfolge (D-Strang, Index §d.1/§d.2): **P1-2 → P1-3 → P1-4 → P1-1**.
Austritt = **Promptfoo-Gate G1–G4 (Index §b, schaltet A1 frei):**
- G1 `cd backend && python manage.py export_promptfoo_configs --check` → Exit 0, letzte Zeile
  `promptfoo export: <n>/<n> slots, 0 missing cases, 0 unresolved placeholders, memory slots covered <b>/<b>`
  mit `<n> = len(get_prompt_slots())` (dynamisch, **keine** feste 23; QR-T07 — neue Slots aus Plan B bringen
  ihre Case-Datei im selben PR mit, der Required Check bleibt grün).
- G2 `pytest application/tests/test_prompt_testing_cases.py application/tests/test_export_promptfoo_configs.py -q` → 0 failed.
- G3 Job `prompt-regression` grün auf dem Merge-Commit in `main` **und** als Required Check eingetragen (D2.5, Nutzer-Gate U-1).
- G4 Negativnachweis (Exit 100) im PR P1-3 verlinkt.
Weitere P1-Austritte (kein A1-Gate): P1-4 — Diff-Scan rot beim Dummy-Geheimnis (verlinkt), danach grün;
D1.0 — `bash frontend/scripts/check-nginx-headers.sh "$QS_URL"` → Exit 0 nach QS-Deploy.

| PR | Branch | Titel | Tasks | Merge | grün auf | Rollback | Größe | Reviewer |
|---|---|---|---|---|---|---|---|---|
| P1-1 | `fix/nginx-security-headers` | `fix(frontend): apply security headers to every nginx response` | D1.0 | 4 (nach P1-4, `ci.yml`-Queue) | `nginx-headers-smoke` (**von diesem PR definiert**; erst ab Merge Check für andere PRs), `frontend-test`, `e2e` (Frontend-Image-Build), `workflow-lint` | Revert, keine Migration | ≈90 | `security-auditor`, `devops-engineer` |
| P1-2 | `feat/promptfoo-export-587` | `feat(prompts): add promptfoo case files and config export` | D2.1, D2.2, D2.3 | 1 | `backend-test` `set-1-core`, `secret-scan` (nur `reqlo_`, KA-ALL-09) | Revert, keine Migration | ≈450 ohne Fall-YAML/Tests — über Richtwert, unter Obergrenze; Split-Option D2.1 ∥ D2.2+D2.3, falls > 400 bleibt | `code-reviewer` |
| P1-3 | `chore/promptfoo-ci-587` | `chore(ci): run promptfoo prompt regression on every PR` | D2.4 | 2 (nach P1-2) | `prompt-regression` (von diesem PR definiert), `agent-templates-test` (Workflow-Vertragstest), `workflow-lint` | Revert | ≈80 (+ Lockfile) | `code-reviewer`, `security-auditor` (Lieferkette, QR-S12) |
| **P1-4** | `fix/secret-scan-env-secrets` | `fix(ci): scan pull requests for env secrets` | D2.6 | 3 (nach P1-3, `ci.yml`-Queue) | `secret-scan` (inkl. neuem Diff-Schritt), `agent-templates-test`, `workflow-lint` | Revert | ≈60 | `security-auditor`, `devops-engineer` |

**P2 — BluePencil B+C (Welle 2).** Eintritt: **ENT-D2 entschieden** (vorläufig B ausgeschrieben, Start erst
nach Entscheidung); ENT-D1/ENT-D3 (vorläufig A); P1-1 gemergt; **Plan A PR-A2 gemergt** (Compose-Queue
A PR-A2 → D P2-1 → G PR 13 → D P3-4, QR-T20). Sicherheitsgate vor Welle 2 (Index §b: QR-S02).
Austritt: QS-Gates aus D1.1/D1.2 (Notizzahl gleich; ohne Sitzung 401, mit Sitzung 200; `latest.json` 0.5.0
mit Lock-SHA; `attach.js` `no-cache`; `bp-attach-ready`); `pytest tests/test_bluepencil_deploy_contract.py -q` grün.

| PR | Branch | Titel | Tasks | Merge | grün auf | Rollback | Größe | Reviewer |
|---|---|---|---|---|---|---|---|---|
| P2-1 | `feat/bluepencil-hub-image-1418` | `feat(deploy): run the bluepencil hub from its pinned image` | D1.1 | 1 (nach A PR-A2; vor G PR 13) | `backend-test` `set-4-features`, `nginx-headers-smoke`, `e2e` (Frontend-Image-Build), `workflow-lint` | Revert stellt `server.js`-Mount und nginx-Location ohne `auth_request` wieder her; Store bleibt (gleicher Pfad); Volume-Owner `node` stört `node:22-slim` als root nicht | ≈250 (+3400 gelöschte Zeilen `server.js`) | `devops-engineer`, `security-auditor` |
| P2-2 | `feat/bluepencil-layer-mount-1418` | `feat(deploy): serve the bluepencil layer from a verified mount` | D1.2, D1.3 | 2 | `frontend-test` (inkl. Fetch), `nginx-headers-smoke`, `backend-test` `set-4-features`, `e2e` | Revert = Dateien wieder im Image (aus Release neu holen) | ≈400 ohne Doku | `code-reviewer`, `devops-engineer` |

**P3-1 — `seed_demo`-Guard (Welle 3, vor Plan E P3-5).** Eintritt: Welle 3 offen; ENT-D9 entschieden oder
vorläufig B. Austritt: Tests grün, `e2e` grün, #89 geschlossen.

**P3 — Restpunkte (Welle 4).** Eintritt: keine Abhängigkeit außer Nutzer-Gates für D5.2/D5.3 (U-5) und
Compose-Queue für P3-4. Austritt: #792 neu gefasst, #1171 Prüftest mit neuen Verboten grün, #92/#1418
geschlossen, `grep -c latest/download .github/workflows/publish-mcp-registry.yml` → 0.

| PR | Branch | Titel | Tasks | Merge | grün auf | Rollback | Größe | Reviewer |
|---|---|---|---|---|---|---|---|---|
| P3-1 | `fix/seed-demo-prod-guard-89` | `fix(auth): require explicit opt-in for the seed_demo password` | D6.2 | **Welle 3, vor Plan E P3-5 (E3.8)** — Queue `seed_demo.py` D P3-1 → E P3-5 | `backend-test` `set-2-api`, `e2e` | Revert | ≈100 | `security-auditor`, `code-reviewer` |
| P3-2 | `feat/setup-preflight-792` | `feat(deploy): add setup script with secret and port preflight` | D3.2 | nach P1-4 (`agent-templates-test`-Befehl) | `agent-templates-test`, `secret-scan` | Revert | ≈170 | `devops-engineer`, `security-auditor` |
| P3-3 | `feat/make-wipe-backup-792` | `feat(deploy): back up off-host before wiping volumes` | D3.3 | beliebig (Rebase auf `ci.yml`-Queue) | `agent-templates-test` (Backup-Prüftest laut KA-D-09); `lint` entfällt (kein Frontend) | Revert | ≈80 | `devops-engineer`, `code-reviewer` |
| P3-4 | `fix/dev-overlay-visibility-792` | `fix(health): expose django_env as health advisory` | D3.4 | nach G PR 13 (Compose-Queue A PR-A2 → D P2-1 → G PR 13 → **D P3-4**) | `backend-test` `set-2-api` | Revert | ≈40 | `code-reviewer` |
| P3-5 | `fix/client-docs-broken-1171` | `fix(docs): repair broken client install instructions` | D4.1 | 1 | `agent-templates-test`, `client-artifacts` (läuft nur bei Pfadtreffer; hier `clients/**`/`docs/clients/**`) | Revert | ≈250 | `code-reviewer`, `documenter` |
| P3-6 | `feat/client-docs-gaps-1171` | `feat(docs): close remaining client documentation gaps` | D4.2 | 2 | wie P3-5 | Revert | ≈250 | `code-reviewer`, `documenter` |
| P3-7 | `feat/claude-plugin-userconfig-1171` | `feat(plugin): configure claude plugin via userConfig` | D4.3 | beliebig (vorläufig ENT-D4 = A) | `agent-templates-test`, `client-artifacts` (Pfadtreffer `dist/**`) | Revert | ≈150 | `code-reviewer` |
| P3-8 | `chore/mcp-publisher-pin-1230` | `chore(ci): pin mcp-publisher release and checksum` | D5.1 | beliebig | `workflow-lint` | Revert | ≈20 | `security-auditor` |
| P3-9 | `feat/server-json-host-template-1230` | `feat(clients): template the MCP registry remote host` | D5.2 | nach U-W3b (vorläufig ENT-D6 = A) | `client-artifacts` (Pfadtreffer `scripts/clients/**`, `server.json`) | Revert | ≈40 | `code-reviewer` |
| P3-10 | `feat/opencode-npm-package-1230` | `feat(clients): generate the opencode npm package` | D5.3 | nach U-W2a | `agent-templates-test`, `client-artifacts` (Pfadtreffer `dist/**`) | Revert | ≈300 | `code-reviewer` |

D6.1 (#92 schließen, Welle 4) ist kein PR: Nachweis-Lauf + Abschlusskommentar (vorläufig ENT-D5 = A).

Regeln: jeder PR referenziert sein Issue (`Fixes #…`; #1171 erst mit P3-6, #1230 bleibt offen bis Nutzer-Gates;
P1-4 referenziert QR-S03/ein per `feedback` angelegtes Issue);
keine Migrationen; kein PR bündelt zwei unabhängige Features (P2-2 bündelt Layer-Auslieferung und deren Doku).

## Verifikationsbefehle (Auszug, erwartete Ausgabe)

| Nach | Befehl | Erwartet |
|---|---|---|
Backend-`pytest` lokal über das Makro aus Index §f.3; QS-Befehle mit `$QS_URL` (Basis-URL der QS) und
`$QS_COOKIE` (Cookie-Datei einer angemeldeten Sitzung) — keine Literal-Adressen.

| Nach | Befehl | Erwartet |
|---|---|---|
| D1.0 | `bash frontend/scripts/check-nginx-headers.sh "$QS_URL"` | Exit 0 (inkl. `frame-ancestors 'none'`, `script-src` ohne `unsafe-*`) |
| D1.0 | CI `nginx-headers-smoke` | grün, Negativfall (manipulierte CSP) liefert Exit 1 |
| D1.1 | `pytest tests/test_bluepencil_deploy_contract.py -q` (backend) | 0 failed |
| D1.1 | `curl -s -o /dev/null -w '%{http_code}' "$QS_URL/bluepencil/api/notes"` | `401` (ohne Sitzung; vorläufig ENT-D2 = B) |
| D1.1 | `curl -s -b "$QS_COOKIE" "$QS_URL/bluepencil/api/health"` | `{"ok":true,"status":"ok","version":"0.5.0"}` |
| D1.2 | `bash deploy/bluepencil/fetch-layer.sh --dest "$RUNNER_TEMP/bp" && cat "$RUNNER_TEMP/bp/latest.json"` (lokal: Ziel unter `.tmp/`) | `"version": "0.5.0"`, `"sha256": "2fe86eda…"` |
| D1.2 | `curl -s -o /dev/null -w '%{http_code}' "$QS_URL/bluepencil/latest/missing.json"` | `404` |
| D2 | `python manage.py export_promptfoo_configs --check` | Exit 0, letzte Zeile `promptfoo export: <n>/<n> slots, 0 missing cases, 0 unresolved placeholders, …` mit `<n> = len(get_prompt_slots())` |
| D2 | `CI=true python manage.py export_promptfoo_configs --deep --provider echo` | `CommandError` „--deep is refused in CI" |
| D2 | CI `prompt-regression` | grün; Required Check laut `gh api …/required_status_checks --jq '.contexts'` |
| D2.6 | `git check-ignore -q .env.bak-test && echo ignored` | `ignored` |
| D2.6 | CI `secret-scan` (Negativ-Commit mit Dummy-Wert) | rot im Diff-Schritt; nach Revert grün |
| D3.2 | `pytest scripts/test_setup_script.py -q` | 0 failed |
| D3.3 | `pytest scripts/test_offhost_backup_check.py -q` | 0 failed |
| D3.4 | `pytest reqogniloom/tests/test_health_django_env_advisory.py -q` | 0 failed |
| D4 | `pytest docs/agent-templates dist -q && python3 scripts/clients/render.py --check` | 0 failed / OK |
| D5.1 | `grep -c 'latest/download' .github/workflows/publish-mcp-registry.yml` | `0` |
| D6.2 | `pytest auth_tenancy/tests/test_seed_demo.py -q` | 0 failed |

## Änderungsprotokoll Stufe 2

Stand 2026-10-21. Quelle: [Korrekturaufträge](2026-10-21-korrekturauftraege.md) Abschnitt D und KA-ALL
(für Plan D zutreffend: KA-ALL-06, -07, -08, -09, -11). „vorläufig" = Empfehlung der Entscheidungsliste
eingesetzt, Stelle im Text mit „vorläufig, ENT-…" markiert.

| Auftrag | Task-/Abschnitts-ID im Plan | Status | Bemerkung |
|---|---|---|---|
| KA-D-01 | (i) Ziel 2; (iii) D2; D2.1; D2.2; (xiii) P1 G1; (viii); (vii); Verifikation | erledigt | Soll-Zahl `len(get_prompt_slots())`, Tests ohne feste 23; 23 nur noch als Messstand-Angabe |
| KA-D-02 | D2.1 (Regel + Test-Docstring); (v) Plan → Plan | erledigt | A erweitert (T-A1-8), B legt `quality_*` im selben PR an (B5-T2); nie roter Case in `main` |
| KA-D-03 | neue Task D2.6; neuer PR P1-4; D3.2; (v); (xii); (xiii) | erledigt | Eintritt Sofortmaßnahme Index §h + ENT-X1 |
| KA-D-04 | D2.2 (`--deep` in CI gesperrt); D2.4; (vii) | erledigt | Lockfile, `npm ci --ignore-scripts`, Rechte, keine Secrets, Workflow-Vertragstest mit CI-Anbindung |
| KA-D-05 | (i); (ii); D1.1; D1.2 (Overlay-Env); D1.3; (vi); (vii); (ix) ENT-D2; P2-1 | vorläufig (ENT-D2 = B) | Start D1 erst nach Entscheidung („Vorläufig: nein"); Variante A′ beschrieben |
| KA-D-06 | D6.2; (vi) | vorläufig (ENT-D9 = B) | Variante A (Untergrenze) beschrieben. Teilabweichung: `playwright.yml` setzt das Opt-in **nicht**, weil CI `SYSTEM_ADMIN_PASSWORD` schon setzt (`:112`) und kein Default-Passwort braucht |
| KA-D-07 | D1.0; (vi) | erledigt | Digest wird bei Umsetzung ermittelt (Platzhalter `<digest>`) |
| KA-D-08 | D4.1 | erledigt | exakte Version `<x.y.z>` ≥ 0.1.16 bei Umsetzung festlegen |
| KA-D-09 | D3.3; (vi); (vii) | erledigt | Prüfskript `deploy/check-offhost-backup.sh` + CI-angebundener pytest |
| KA-D-10 | Kopf „Wellen"; WP D6; D6.2; (v); (xii); (xiii) P3-1 | erledigt | D6.2 Welle 3 vor E3.8, D6.1 Welle 4 |
| KA-D-11 | D1.1; D3.4; (v); (xii); (xiii) P2-1, P3-4 | erledigt | Compose-Queue A PR-A2 → D P2-1 → G PR 13 → D P3-4 |
| KA-D-12 | (xiii) Vorspann + Spalten „grün auf" | erledigt | P1-1 definiert `nginx-headers-smoke`; P3-3 ohne `lint`; `client-artifacts` nur bei Pfadtreffer |
| KA-D-13 | (ii); (ix); Eintritte; D1.2; (xii); alle `D-D*`-Verweise | erledigt | `D-D1…D8` → `ENT-D1…D8`, neu ENT-D9; Rolle `frontend-component-engineer` |
| KA-ALL-06 | (xiii) Vorspann + PR-Tabellen | erledigt | nur reale Jobs (Index §f.2) |
| KA-ALL-07 | Kopf; (xiii) Vorspann; QS-Befehle (`$QS_URL`, `$QS_COOKIE`) | vorläufig (ENT-X3 = C) | interne Adressen aus Verifikationsbefehlen und ENT-D2-Zeile entfernt |
| KA-ALL-08 | (xiii) Vorspann; P1-2 Größe | erledigt | P1-2 über Richtwert, Split-Option benannt |
| KA-ALL-09 | (xiii) Vorspann; P1-2 | erledigt | gilt bis Merge P1-4 |
| KA-ALL-11 | D1.2; (xii) | erledigt | keine weiteren nicht existierenden Rollen im Plan |

Summe: 18 Aufträge — 15 erledigt, 3 vorläufig (KA-D-05, KA-D-06, KA-ALL-07), 0 abgelehnt.
