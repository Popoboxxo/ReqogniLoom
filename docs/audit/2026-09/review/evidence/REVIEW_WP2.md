---
type: REVIEW
scope: "WP-2 (Native Plugins) — adversarial second review"
status: final
date: 2026-10-01
author_agent: code-reviewer
branch: chore/audit-review-2026-09
method: "Read-only adversarial verification against real product source at HEAD 10dc620f; audit-owned AUDIT_EVIDENCE/* explicitly NOT used as proof. Static code derivation primary; live partial checks against the running Docker stack (localhost:8001, Bluepencil sidecar, Postgres) where statically impossible. Numbers re-counted from code/DB."
targets:
  - AUD-2026-09-115
  - AUD-2026-09-100
  - AUD-2026-09-101
  - AUD-2026-09-109
  - AUD-2026-09-110
  - AUD-2026-09-114
  - AUD-2026-09-117
  - AUD-2026-09-102
  - AUD-2026-09-106
  - AUD-2026-09-107
  - AUD-2026-09-111
  - AUD-2026-09-112
  - AUD-2026-09-113
  - AUD-2026-09-103
  - AUD-2026-09-104
  - AUD-2026-09-105
  - AUD-2026-09-108
  - AUD-2026-09-116
  - AUD-2026-09-150
  - AUD-2026-09-151
  - AUD-2026-09-152
  - AUD-2026-09-153
---

# REVIEW_WP2 — adversarial second review of the WP-2 native-plugin findings

## 1. Scope und Methodik

Gegenstand: der WP-2-Finding-Block (`docs/audit/2026-09/AUDIT_FINDINGS.md`
§3 Master-Tabelle / §5 Volltext, Detailtabelle in
`docs/audit/2026-09/AUDIT_NATIVE_PLUGINS.md` §3). Zielblock 100–119 (Critical 115,
High 100/101/109/110/114/117, Medium-Stichprobe 102/106/107/111/112/113,
Low-Stichprobe 103/104/105/108/116) plus Info 150–153. **n = 22.**

Vorgehen (verbindliches Protokoll):

1. Jede zitierte `datei:zeile` am HEAD `10dc620f` lokalisiert und wörtlich geprüft.
2. Jede Aussage gegen Unabhängigkeit geprüft (produkt-code-abgeleitet); das
   audit-eigene `AUDIT_EVIDENCE/wp2-*` wurde **nicht** als Beweis verwendet.
3. Gegenbeweis bzw. Stützcode wörtlich mit `datei:zeile` belegt. Fehlzitate
   werden auch dann notiert, wenn die Aussage im Kern überlebt.
4. Zahlen ("210 Tests", "106 Py + 104 TS", "80/80, 82/82, 129/129", "401
   Workspaces", "25 erreichbar", "219 Registry") neu gezählt — Testfälle per
   Regex, Workspaces/Seiten über die laufende Postgres-Instanz
   (`pl_workspace`, `pl_tenant`) und `PAGE_SIZE`.
5. Read-only: keine Produkt-, Test- oder Konfigurationsdatei geändert; einziges
   Schreibziel ist diese Datei. `.kimi-code/` und `stack-seeds.md` nicht berührt.

Live-Teilstücke (ausdrücklich als solche markiert): `GET /api/v1/version/`,
`/bluepencil/api/notes` über das Compose-Netz, DB-Zählungen.

---

## 2. Gegenbeweis-Tabelle (n = 22)

| ID | orig | Verdikt | korr. Sev | Gegenbeweis (`datei:zeile` + Zitat) | Notiz |
|---|---|---|---|---|---|
| AUD-115 | Critical | **BESTAETIGT** | Critical | `integrations/hermes-agent-plugin/__init__.py:79` `lines.append(f"missing:   {', '.join(missing)}")`; `:77-78` `missing = state.get("missing_fields") or []` / `if missing:`; Aufrufer `:110` `_fmt_state(session)`, `:120` `_fmt_state(client.get_state(session_id))`, `:127` `_fmt_state(result)`; Fang nur `:162` `except ReqogniLoomError as exc:`. Server liefert `backend/application/interview_service.py:392` `return {"name": f.name, "type": f.type, "choices": f.choices}` und `:428` `"missing_fields": [self._serialise_field(f) for f in missing]` — also **Dicts**, nicht Str. Docstring `:87-88` "Never raises — every error path returns a human-readable string instead." | Mechanik, Zeilennummern und Pfad exakt belegt. `start`/`status`/`answer` sind erreichbar (jede frische Single-Session hat nicht-leere `missing_fields`). Typischer Python-Fehler `TypeError: sequence item 0: expected str instance, dict found`; nicht gefangen ⇒ Widerspruch zum Docstring bestätigt. Geltung auf das optionale POC-Plugin begrenzt. |
| AUD-100 | High | **BESTAETIGT** | High | `.gitignore:2` `dist/`; `git check-ignore -v` ⇒ `integrations/hermes-plugin/reqogniloom/.gitignore:2:dist/  integrations/hermes-plugin/reqogniloom/dist/plugin.js`; `git ls-files .../dist/` ⇒ leer. `hermes-plugin.json:7` `"main": "dist/plugin.js"`. `docs/agent-templates/INSTALL.md` (165 Z.) enthält keinen Hermes-Abschnitt (nur Claude Code / OpenCode / Antigravity; 0 Treffer "Hermes"). | Beide Teilaussagen bestätigt. Nuance: das Gitignorieren eines Build-Artefakts ist konventionell; der eigentliche Handlungsbedarf ist die fehlende Install-Doku. Kein REQ-Bezug. |
| AUD-101 | High | **UEBERZOGEN** | **Low** | `docs/superpowers/specs/Archive/2026-08-13-hermes-ide-plugin-design.md:44-49`: "`hermes-hq/plugins`' own `plugins/github/` plugin (`hermes-plugin.json` + `src/activate.ts` …) is the closest analog … reused as the structural template"; `:51-74` zeigt genau dieses `hermes-plugin.json`-Schema (`main`, `activationEvents`, `contributes`, `permissions`) als **Soll**. Das `{name, api}`-Schema ist dagegen die **Agent/Dashboard**-Manifest-Form: `integrations/hermes-agent-plugin/dashboard/manifest.json:1-11` `{ "name", …, "api": "plugin_api.py" }`. | Die Aussage "VS-Code-Schema, nicht der Hermes-Vertrag" verwechselt den Desktop-Plugin-Manifesttyp (`hermes-plugin.json`, belegt am Hermes-Referenzplugin) mit dem Agent-Dashboard-Manifest (`manifest.json`, das das Python-Plugin nutzt). Der Kern (Host-Vertrag unverifiziert, SDK "locally transcribed") ist bereits als BLOCKED erfasst. High nicht tragfähig → Low. |
| AUD-109 | High | **BESTAETIGT** | High | `src/api.ts:149-152`: Prüfung nur auf `results`-Array, `return (body as WorkspaceListResponse).results;` — `next` (deklariert `:18`) wird nie gelesen. `reqogniloom_client.py:136-139` `return _list_results(self._request("GET", path), path)`; `_list_results` (`:37-51`) liest ebenfalls nur `results`. Server: `backend/rest_api/serializers.py:360` `page_size = 25` / `:537` `PAGE_SIZE: 25`; `backend/application/workspace_service.py:174` `return Workspace.objects.all().order_by("-modified_at")`. | Zahlen live bestätigt: `pl_workspace` = **401** Zeilen (alle Tenant `7a539397…`). Der im Audit benannte Demo-Workspace `4eee7ca1-eedd-4a7e-bb14-47e6493cbf88` ("Zahnbürste SysEng Demo") ist per `-modified_at`-Ranking **Rang 400 von 401** ⇒ erst auf Seite 16 ⇒ über beide Plugins unerreichbar. "25 von 401" exakt. |
| AUD-110 | High | **UEBERZOGEN** | **Medium** | `__init__.py:62` `start <artifact_type> [workspace_id]   Start a new interview (e.g. "requirement", "need").`; Test `tests/test_slash_command.py:45` `plugin._handle_slash("start requirement")`. Server lehnt ab: `backend/application/interview_service.py:180-183` `if artifact_type not in IN_SCOPE_ARTIFACT_TYPES: raise ValidationError(f"Interviews are not available for artifact_type={artifact_type!r} …")`; `interview_protocol.py:31-32` `IN_SCOPE_ARTIFACT_TYPES = ("Requirement", …)`. | Mechanik bestätigt (kein Normalisieren, nur PascalCase). Aber der Server antwortet mit einem klaren `400 VALIDATION_ERROR` und Namensnennung; kein stiller Fehlschlag. Wirkung = Doku-/UX-Fehler, High überzogen → Medium. |
| AUD-114 | High | **TEILWEISE** | High | `tests/test_slash_command.py:40` `"missing_fields": ["title"],` ist eine **String**-Liste; der Server liefert Dicts (`interview_service.py:392`). `api.test.ts:8-9` `count: 1, next: null`, `:31` `next: null`, `:42-43`, `:62-63` — Fixture kodiert "eine Seite". | Der Python-Teil ist stark: das Fixture verdeckt genau den AUD-115-Crash. Der TS-Teil ist schwächer: `listWorkspaces` ignoriert `next` ohnehin, das Fixture behauptet keinen Gesamtumfang; es deckt nur "eine Seite" ab. Zahl "210" vollständig reproduziert (s.u.). High (verdeckt 1 Critical + 1 High) gerechtfertigt, aber Formulierung "kodieren einen Vertrag, den der Server nicht erfüllt" nur für die Python-Hälfte wörtlich. |
| AUD-117 | High | **UEBERZOGEN** | **Medium** | `state.ts:196-198` `catch (err) { setState({ interviewBusy: false, interviewError: … }); }` — `view` bleibt dabei auf `"connected"`. `ReqogniLoomPanel.tsx:56-59` rendert `view==="connected"` ausschließlich `<ConnectedView>`; `ConnectedView.tsx:6-24` enthält **kein** `ErrorBanner`. `InterviewListView.tsx:25` rendert `<ErrorBanner message={state.interviewError} />` — wird aber nur bei `view==="interviews"` gebaut. | Mechanik exakt bestätigt: der Fehler ist im Connected-Zustand unsichtbar, `openInterviews()` scheitert stumm. Wirkung = ein stiller Fehlschlag eines Buttons, keine Daten-/Sicherheitsfolge → High überzogen (konsistent mit anderen Medium-"silent failures") → Medium. |
| AUD-102 | Medium | **BESTAETIGT** | Medium | `hermes-plugin.json:14-20` `contributes.commands[].command = "reqogniloom.open"`; `:36` `statusBarItems[].command = "reqogniloom.open"`. `src/activate.ts:60-75` registriert nur zwei Descriptors: `:61` `id: PANEL_ID, area: "panes"` und `:71` `id: STATUS_BAR_ID, area: "statusBar.right"` — **kein** `area: "commandPalette"`. `src/hermes-sdk-types.ts:29-34` definiert `HermesCommandDescriptor`/`"commandPalette"`, nie instanziiert. | Bestätigt: die deklarierte Command-ID wird nirgends registriert. Host-seitig (liest Hermes `contributes`?) nicht verifizierbar, im Repo-Code aber eindeutig kein Command-Handler. |
| AUD-106 | Medium | **BESTAETIGT** | Medium | `integrations/hermes-agent-plugin/plugin.yaml:2` `version: 0.1.0`; `dashboard/manifest.json:6` `"version": "0.1.0"`. `dist/plugins/hermes/build_hermes_plugin.py:20` `PLUGIN_ROOT = REPO_ROOT / "integrations" / "hermes-plugin" / "reqogniloom"`; `:28-43` aktualisiert nur `package.json` + `hermes-plugin.json`. | Bestätigt: Versions-Drift `0.1.0` vs. `VERSION`=1.8.0-beta.17 und der Builder erfasst das Python-Plugin nicht. |
| AUD-107 | Medium | **BESTAETIGT** | Medium | `backend/mcp_server/protocol_handler.py:503-505` `"serverInfo": { "name": "ReqogniLoom", "version": "1.0.0" }`; `backend/mcp_server/views.py:431` `"version": "1.0.0",` in der HTTP-Discovery. `VERSION`=1.8.0-beta.17 (package.json:3, Manifest:4). | Hartkodiert bestätigt, unabhängig von `VERSION`. Live-Volltext (initialize) nicht separat gezogen — statisch eindeutig. |
| AUD-111 | Medium | **BESTAETIGT** | Medium | `__init__.py:138` `return f"Formalized. Artifact: {result.get('artifact_id', result)}"`. Server: `interview_service.py:1292` `return {"resulting_artifact_ids": resulting_ids, "status": session.status}` — der Schlüssel `artifact_id` existiert nicht, daher wird das rohe Dict ausgegeben. Der TS-Client kennt den echten Vertrag: `mcpClient.ts:168-176` `Promise<{ resulting_artifact_ids: string[]; status: string }>`. | Bestätigt. |
| AUD-112 | Medium | **BESTAETIGT** | Medium | `backend/rest_api/interview_views.py:207-209` `return Response({"results": [_session_to_dict(...) for s in sessions]})` — **kein** `count`. Client: `reqogniloom_client.py:54-60` `_total_count` liefert nur bei int-`count` einen Wert, sonst `None`; `:197-204` `open_interviews = _total_count(interviews)`. | Bestätigt: `/interviews/` hat kein DRF-`count`, `open interviews` bleibt dauerhaft `None`. |
| AUD-113 | Medium | **BESTAETIGT** | Medium | `dist/plugins/claude-code/reqogniloom/skills/interview-management/SKILL.md:20-42` instruiert `interview.start/get_state/answer/grounding_context/set_target/formalize`. In `dist/plugins/claude-code/reqogniloom/agents/*.md` = **0** Treffer für `interview.`; die 5 Agenten whitelisten nur `mcp__reqogniloom__<artefakt>.*`. `tool-manifest.json`: genau 10 `interview.*`-Tools. | Statisch bestätigt: alle 10 interview-Tools außerhalb jeder Rollen-Whitelist. "Unbenutzbar" ist eine Host-Verhaltens-Inferenz (setzt voraus, dass Skills unter einer Rollen-Whitelist laufen) — Host ist BLOCKED. |
| AUD-103 | Low | **BESTAETIGT** | Low | `hermes-plugin.json:40-42` `"engines": { "hermes": ">=3.0.0" }`, `:43-46` `"permissions": ["network","storage"]`; `Select-String`/`git grep` über `integrations/.../src` und `hermes-agent-plugin` ⇒ **0** Lesezugriffe auf `engines`/`permissions`. | Im Repo-Code dekorativ bestätigt. Ob der Hermes-Host sie liest, bleibt host-seitig (BLOCKED). |
| AUD-104 | Low | **BESTAETIGT** | Low | `hermes-plugin.json` (gesamtes Dokument, 47 Z.) enthält kein `capabilities`, kein `tools`, kein `minHostVersion`. | Bestätigt. |
| AUD-105 | Low | **BESTAETIGT** | Low | `hermes-plugin.json` hat kein `auth`-Feld; Tokenquelle ist ausschließlich das UI-Formular: `src/ConnectScreen.tsx:19` `const [apiKey, setApiKey] = useState("");`, `:55` `type="password"`. | Bestätigt. |
| AUD-108 | Low | **BESTAETIGT** | Low | Live `GET /api/v1/version/` ⇒ `{"app_version":"unknown","commit_short":"unknown"}`. Code: `backend/reqogniloom/version.py:89-103` — `APP_VERSION`-Env (compose-Default `unknown`) wird als "nicht gesetzt" behandelt, danach VERSION-Datei, zuletzt `_UNKNOWN`. | Live bestätigt. Laufende Instanz kann ihre Version nicht belegen. |
| AUD-116 | Low | **BESTAETIGT** | Low | `src/api.ts:113` `const REQUEST_TIMEOUT_MS = 15_000;`; `src/state.ts:140` `connectError: err instanceof ReqogniLoomApiError ? err.message : "Connection failed."` — Timeout (`AbortSignal.timeout` ⇒ `DOMException`) und `TypeError` (connection refused) sind **keine** `ReqogniLoomApiError` ⇒ identischer Fallback. `mcpClient.ts:60` gleicher 15-s-Wert. | Mechanismus bestätigt. Die exakte Dauer "15005 ms" ist ein Laufzeitwert (nicht statisch nachvollzogen), die Gleichbehandlung beider Fehlerklassen ist es sehr wohl. |
| AUD-150 | Info | **BESTAETIGT** | Info | `.env.example:511` `# COMPOSE_PROFILES=bluepencil`, `:515` `BLUEPENCIL_ENABLED=0`; `deploy/docker-compose.override.yml:196` `VITE_BLUEPENCIL_ENABLED: ${BLUEPENCIL_ENABLED:-0}`; laufender Frontend-Container: `VITE_BLUEPENCIL_ENABLED=0`. Loader `frontend/src/bluepencil/loader.ts:58` `return import.meta.env.VITE_BLUEPENCIL_ENABLED === "1";`. | Bestätigt in der Wirkung (Layer hart-off). Präzisierung: `VITE_BLUEPENCIL_ENABLED` "fehlt" nicht im Repo — es wird in der Override-Datei aus `BLUEPENCIL_ENABLED` gemappt; der Register-Ort nennt diese Override-Zeile nicht. |
| AUD-151 | Info | **BESTAETIGT** | Info | Live über das Compose-Netz (kein Host-Port): `docker exec ai-native-reqflow-poc-frontend-1 node -e "fetch('http://bluepencil:8787/bluepencil/api/notes')…"` ⇒ `STATUS 200`, Body `{"notes":[{"id":"n-8e46…","author":"anonymous","route":"/", …}]}` — **ohne** Credential. `GET http://localhost:8001/bluepencil/api/notes` ⇒ 404 (kein Host-Port, konsistent). | Bestätigt: 200 ohne jede Credential, globaler Store ohne Workspace-/Tenant-Scoping. Der Compose-Kommentar `deploy/docker-compose.yml:1319-1322` nennt genau diese "notes of EVERY workspace, with no RLS/TenantContext scoping". |
| AUD-152 | Info | **KEIN REQOGNILOOM-BEZUG** | Info | `AUDIT_FINDINGS.md:462` / `AUDIT_NATIVE_PLUGINS.md:108` klassifizieren die **Vorab-Track CR-24** als WIDERLEGT ("nicht live verifizierte Verträge ist überholt"). Die Aussage betrifft die Audit-Einordnung, nicht Produktverhalten. | Reiner Audit-/Track-Prozessgegenstand. Der produktrelevante Gehalt ist vollständig in AUD-115 (Python-Hauptpfad bricht) und AUD-119 (zweite Auth-Konvention) abgedeckt. Für den Produkt-Scope nicht bewertbar. Zusatz: "beide **sind** live verifizierbar" ist seinerseits überzogen — das Laden des TS-Bundles in einen echten Hermes-Desktop-Client bleibt BLOCKED (Host nicht installiert); live testbar sind die HTTP-Aufrufe, nicht die Host-Integration. |
| AUD-153 | Info | **TEILWEISE** | Info | `dist/plugins/hermes/` enthält real nur `build_hermes_plugin.py`, `test_build_hermes_plugin.py` (+`__pycache__`) — kein `reqogniloom/`-Artefakt: bestätigt. **Aber** "im Repo nirgends aufgelöst" ist falsch: `dist/test_full_regeneration.py:150` `[sys.executable, "dist/plugins/hermes/build_hermes_plugin.py", "--plugin-root", …]` und `dist/test_mcp_convention_parity.py:495` `DIST_DIR / "plugins/hermes/build_hermes_plugin.py"` referenzieren und führen den Builder aus. | Erste Teilaussage bestätigt, zweite falsch ⇒ TEILWEISE. |

---

## 3. Register-Quercheck

1. **Register §3 vs. Report §3 — Klassifikation 150/151.** Register
   `AUDIT_FINDINGS.md:460-461` führt AUD-150 und AUD-151 mit Klassifikation
   **NEU**; `AUDIT_NATIVE_PLUGINS.md:106-107` und dessen §Klassifikation
   (`:130`) führen beide als **BESTAETIGT**. Das ist ein echter Register/Report-
   Widerspruch. Meine Zweitprüfung stützt **BESTAETIGT** (beide live nachgestellt);
   die Register-Klassifikation ist die fehlerhafte Seite.

2. **§5-Ortsangabe AUD-115.** Register `:626` und `:199` zitieren
   `__init__.py:79` via `:110,:120,:127`. Zeilengenau geprüft: `:79` ist
   `', '.join(missing)`, `:110/:120/:127` sind die drei `_fmt_state(...)`-Aufrufer.
   Die Register-Angabe ist korrekt (die Audit-Vorlage sprach von ":87-88/79/162",
   das Register normalisiert auf `:79`+Aufrufer).

3. **§3-Ortsangabe AUD-101.** Register `:232` zitiert `hermes-plugin.json:8-46`.
   Die Zeilen existieren, die daraus gezogene Schlussfolgerung ("VS-Code-Schema
   statt Hermes-Vertrag") ist aber falsch (siehe Tabellenzeile, Design-Spec
   `:44-74`). Fehlschluss, kein Fehlzitat.

4. **§1c-Zahlen im Report.** Unabhängig nachgezählt:
   * "80/80 Agent-Tools": `dist/plugins/claude-code/reqogniloom/agents/*.md`
     ⇒ 124 Referenzen, davon **80 unique** ⇒ bestätigt.
   * "129/129 `skills-tool-refs.json`": `docs/agent-templates/skills-tool-refs.json`
     ⇒ 31+14+15+39+25+5 = **129** ⇒ bestätigt.
   * "219er-Registry": `tool-manifest.json` `tool_count=219`, `len(tools)=219`
     ⇒ bestätigt.
   * "82/82 Skill-Text-Referenzen": mit einem naiven Tool-Token-Extraktor über
     `dist/plugins/*/reqogniloom/skills/*/SKILL.md` erhalte ich **87 unique**,
     nicht 82. Ohne die audit-eigene Extraktionsmethode (darf nicht als Beweis
     dienen) ist die 82 **nicht exakt reproduzierbar** → NICHT VERIFIKABAR
     (fehlender Prüfschritt: Definition "Skill-Text-Referenz").

5. **"210 grüne Tests (106 Py + 104 TS)".** Unabhängig gezählt:
   Python `def test_` = **106** (`test_plugin_api.py` 59 + `test_reqogniloom_client.py`
   36 + `test_slash_command.py` 11). TypeScript: 92 reguläre `it(` + 3 `it.each`
   ⇒ 95 Blöcke, expandiert (2 + 2 + 8) = **104**. Summe **210** ⇒ bestätigt.
   "grün" selbst nicht ausgeführt (read-only), Zählung exakt.

---

## 4. Verdikt-Zählung (n = 22)

| Verdikt | Anzahl | IDs |
|---|---|---|
| BESTAETIGT | 16 | 115, 100, 109, 102, 106, 107, 111, 112, 113, 103, 104, 105, 108, 116, 150, 151 |
| TEILWEISE | 2 | 114, 153 |
| UEBERZOGEN | 3 | 101 (High→Low), 110 (High→Medium), 117 (High→Medium) |
| FALSCH | 0 | — |
| UNTERSCHAETZT | 0 | — |
| NICHT VERIFIKABAR | 0 (1 Report-Zahl offen, s. §3.4) | — |
| KEIN REQOGNILOOM-BEZUG | 1 | 152 |

**Schweregrad-Korrekturen: 3** (101, 110, 117 — alle High herabgestuft).
**Fehlzitate: 0** im engeren Sinn; **eine falsch gezogene Schlussfolgerung** (101)
und **eine zu weit gefasste Orts-/Wirkungsangabe** (150, Override-Zeile fehlt).

---

## 5. Key-Verdikte

1. **AUD-115 BESTAETIGT (Critical bleibt).** Der Hauptpfad ist real defekt:
   `_fmt_state` (`__init__.py:75-83`) joint `missing_fields`, die der Server als
   Dicts liefert (`interview_service.py:392,428`); `except ReqogniLoomError`
   (`:162`) fängt den `TypeError` nicht. Erreichbar für `start` (Zeile 110),
   `status` (120) und `answer` (127), weil eine frische Single-Session immer
   nicht-leere `missing_fields` hat. Das Docstring-Versprechen `:87-88` ist
   gebrochen. Der Befund ist der stärkste des WP-2.

2. **AUD-109 BESTAETIGT (High).** Beide Clients lesen nur `results`
   (`api.ts:149-152`; `reqogniloom_client.py:136-139`) und ignorieren `next`.
   Mit `PAGE_SIZE=25` (`serializers.py:360`) und **401** Workspaces ist der
   Ziel-Workspace `4eee7ca1…` (`-modified_at`-**Rang 400**) unerreichbar. Die
   Zahl "25 von 401" ist exakt; die Live-DB bestätigt sie.

3. **AUD-101 UEBERZOGEN (High→Low).** Die Behauptung verwechselt zwei
   Manifest-Typen. Das `hermes-plugin.json`-Schema ist laut repo-eigener
   Design-Spec (`:44-74`) genau das Muster des realen Hermes-Referenzplugins
   (`hermes-hq/plugins/github`); das `{name, api}`-Schema gehört zum
   Agent-Dashboard-Manifest (`dashboard/manifest.json:1-11`). Kein
   Manifest-Defekt belegbar.

4. **AUD-110 / AUD-117 UEBERZOGEN (High→Medium).** Beide Mechanismen stimmen
   (keine `artifact_type`-Normalisierung; `interviewError` unsichtbar in
   `view==="connected"`), aber die jeweils erzielte Wirkung ist ein sichtbarer
   400 bzw. ein stiller Ein-Button-Fehlschlag — High ist zu hoch.

5. **AUD-112 / AUD-111 / AUD-113 BESTAETIGT.** Drei präzise Vertragsbrüche
   (`/interviews/` ohne `count` ⇒ `open_interviews=None`; `artifact_id` statt
   `resulting_artifact_ids`; 10 interview-Tools in keiner Rollen-Whitelist) sind
   zeilengenau belegt.

6. **AUD-150 / AUD-151 BESTAETIGT (Info).** Bluepencil-Sidecar live: gesund,
   `/bluepencil/api/notes` liefert **200 ohne Credential** mit globalen Notizen.
   Frontend `VITE_BLUEPENCIL_ENABLED=0` ⇒ Layer hart-off. Präzisierung: das
   Mapping `VITE_BLUEPENCIL_ENABLED: ${BLUEPENCIL_ENABLED:-0}` liegt in
   `deploy/docker-compose.override.yml:196`, nicht an den Register-Orten.

---

## 6. NEU-AUDIT-LUECKE (nicht im Register/Target-Block)

1. **Register-Klassifikationsdrift 150/151 (Register NEU vs. Report BESTAETIGT).**
   Siehe §3.1. Das Register selbst widerspricht dem WP-2-Report. → **Neu, Low
   (Prozess)**.

2. **`hermes-plugin.json` deklariert `main: dist/plugin.js`, aber `package.json`
   hat kein `main`-Feld.** `package.json` (30 Z.) enthält kein `"main"`; der
   Builder-Test `dist/plugins/hermes/test_build_hermes_plugin.py:108` prüft
   `main` in `package.json` nur `if key in committed_package` und deckt die
   Lücke damit nicht ab. Je nach Host-Resolver (liest Hermes `hermes-plugin.json`
   oder `package.json`?) ist der Einstiegspunkt dann undefiniert. → **Neu, Low**
   (Teilmenge von AUD-100/101).

3. **AUD-110-Hilfetext und POC-Realität differieren zusätzlich in der Groß-/Klein-
   schreibung der Start-Buttons.** `InterviewListView.tsx:8-11` nutzt korrekt
   PascalCase (`"Requirement", …`), während der Python-Hilfetext
   (`__init__.py:62`) und der Python-Test (`test_slash_command.py:45`) lowercase
   verwenden. Die beiden Plugin-Oberflächen sind damit inkonsistent; nur ein
   Hinweis, keine neue Schwere. → **Neu, Low.**

4. **Der 82/82-Wert des Reports ist ohne dokumentierte Extraktionsmethode nicht
   reproduzierbar** (naive Zählung: 87). Entweder Methode nachliefern oder die
   Zahl als Näherung kennzeichnen. → **Neu, Low (Prozess).**

---

## Anhang — geprüfte, aber nicht veränderte Stellen

* `integrations/hermes-agent-plugin/tests/_loader.py` (Lademechanik der Py-Tests) — nicht gegen den Live-Vertrag, nur lokal.
* `integrations/hermes-plugin/reqogniloom/scripts/verify-build.mjs` — Build-Guard; nicht Teil der Findings.
* `frontend/src/bluepencil/loader.ts:58` — bestätigt die Hard-off-Bedingung (`=== "1"`).
* `deploy/docker-compose.yml:1319-1325` — Compose-Kommentar dokumentiert die fehlende Tenant-Isolation selbst.
* `docs/superpowers/specs/Archive/2026-08-13-hermes-ide-plugin-design.md` — von der Audit-Referenz **nicht** herangezogen; widerlegt die AUD-101-Prämisse.
