---
type: REVIEW
scope: wp-2-native-plugins
status: final
date: 2026-09-29
author_agent: senior-developer
---

# WP-2 — Tiefenaudit der nativen Plugins/Integrationen

**Ampel: ROT** — 24 Findings: 1 Critical, 6 High, 7 Medium, 6 Low, 4 Info

Geprüft: `integrations/hermes-plugin/` (TS-Desktop), `integrations/hermes-agent-plugin/`
(Python-Agent — im Auftrag nicht genannt, physisch vorhanden),
`dist/plugins/antigravity/`, `dist/plugins/claude-code/`, `dist/plugins/hermes/`,
sowie die Bluepencil-Host-Bridge aus `CR-25`.

**Reine Audit-Arbeit.** Keine Produkt-Änderung. Einzige Schreibvorgänge: dieses
Dokument, drei `AUDIT_EVIDENCE/wp2-plugin-*.md`, das Build-Artefakt
`integrations/hermes-plugin/reqogniloom/dist/plugin.js` (gitignored, vom
dokumentierten `npm run build` erzeugt) und die Audit-Artefakte in der laufenden
Instanz (s. Evidenz 3 §8 — alle zurückgeräumt).

**Evidenz-Dateien**

| Datei | Inhalt |
|---|---|
| `AUDIT_EVIDENCE/wp2-plugin-inventory-and-manifest-matrix.md` | Inventar, Manifest-Feldmatrix, Versions-Sync, Discovery, Security-Scan, BLOCKED-Liste |
| `AUDIT_EVIDENCE/wp2-plugin-capability-reconciliation.md` | Fähigkeits-Abgleich deklariert/Code/Registry/live, Testabdeckung |
| `AUDIT_EVIDENCE/wp2-plugin-e2e-and-secret-handling.md` | E2E-Protokoll, Fehlerpfade, Secret-Handling, Bluepencil-Messung |

---

## 1. Antwort auf die drei Kernfragen vorab

**(a) Welche Plugins waren live end-to-end testbar?**
Alle vier lauffähigen Bundles waren live testbar — die Hermes-TS- und die
Hermes-Python-Integration über **echte, vom Plugin selbst erzeugte Requests** gegen
`http://localhost:8001`; Claude Code und Antigravity über den vollständigen
SSE-Handshake, den ihre Manifeste konfigurieren. **Kein Plugin musste als BLOCKED
abgewertet werden**, weil der Server unerreichbar gewesen wäre. Blockiert bleiben
nur fünf *Host-seitige* Fragen (Evidenz 1 §6, Evidenz 3 §9) — also Aussagen über
den Hermes-/Claude-/Antigravity-Client, nicht über die Plugins.

**(b) Versions-Sync?** **PASS für alle Plugin-Manifeste, FAIL an zwei Stellen außerhalb
der Plugin-Manifeste.** Alle generierten Manifeste, `package.json`,
`package-lock.json` und `hermes-plugin.json` stehen auf `1.8.0-beta.17` == `VERSION`.
Drift: das Python-Plugin (`0.1.0`, von keinem Builder erfasst) und die hartkodierte
MCP-`serverInfo.version` (`1.0.0`). **Die Auftragsprämisse `1.8.0-beta.18` existiert
nirgends im Repo** — der letzte Release ist `v1.8.0-beta.17`.

**(c) Kernfrage deklarierte Fähigkeiten vs. Realität?** Für die `dist/`-Pakete:
**0 Über-Deklarationen, 0 Phantom-Tools** (80/80 Agent-Tools in der Registry, 82/82
Skill-Text-Referenzen in der Registry, 129/129 `skills-tool-refs.json`-Referenzen in
der Registry). Für das **Hermes-Python-Plugin: 8/8 Endpunkte existieren, aber die
dokumentierten Beispielwerte und der Hauptnutzungspfad sind defekt**
(→ 110, 115). Für das Hermes-TS-Plugin: **7/7 MCP-Calls real** (→ 1a).

---

## 2. Inventar

Fünf Bundles, nicht drei (Details Evidenz 1 §1):

| # | Bundle | Pfad | Versioniert | Auslieferbar |
|---|---|---|---|---|
| 1 | Hermes TS Desktop | `integrations/hermes-plugin/reqogniloom/` (14 Dateien) | ✔ | ✖ **Bundle gitignored** |
| 2 | Hermes Python Agent | `integrations/hermes-agent-plugin/` (7 Dateien) | ✔ | ✔ |
| 3 | Claude Code | `dist/plugins/claude-code/` (13) | ✔ | ✔ |
| 4 | Antigravity | `dist/plugins/antigravity/` (10) | ✔ | ✔ |
| 5 | Hermes Dist-Builder | `dist/plugins/hermes/` (2) | ✔ | **kein Artefakt** |

* **`dist/` ist versioniert** (56 Tracker-Dateien) — die vermutete
  Reproduzierbarkeets-Lücke besteht dort **nicht**.
* **Keine leeren oder Platzhalter-Verzeichnisse** unter `integrations/` und `dist/`.
* Das **gebaute** TS-Bundle `dist/plugin.js` — der im Manifest deklarierte
  `main`-Einstiegspunkt — ist **gitignored** und wird in keinem
  Installationsdokument erwähnt (INSTALL.md hat keinen Hermes-Abschnitt).

---

## 3. Findings

| ID | Severity | Klassifikation | CR/Issue | Ort | Kurztitel |
|---|---|---|---|---|---|
| AUD-2026-09-115 | **Critical** | NEU | — (CR-24 verwandt) | `integrations/hermes-agent-plugin/__init__.py:79` (via `:110,:120,:127`) | `_handle_slash` wirft `TypeError` — dokumentiert „never raises"; `start`/`status`/`answer` brechen live |
| AUD-2026-09-100 | **High** | NEU | — | `integrations/hermes-plugin/reqogniloom/hermes-plugin.json:7` + `.gitignore:2` | `main: dist/plugin.js` ist gitignored; Hermes-Installation komplett undokumentiert |
| AUD-2026-09-101 | **High** | NEU | CR-24 | `integrations/hermes-plugin/reqogniloom/hermes-plugin.json:8-46` | Manifest ist VS-Code-Schema, nicht der Hermes-`manifest.json {name, api}`-Vertrag |
| AUD-2026-09-109 | **High** | NEU | — | `…/src/api.ts:143-153`; `integrations/hermes-agent-plugin/reqogniloom_client.py:136-139` | Beide Plugins lesen nur `results[]`, ignorieren `next` → Ziel-Workspace live unerreichbar (25 von 401) |
| AUD-2026-09-110 | **High** | NEU | — | `integrations/hermes-agent-plugin/__init__.py:62,105-107` | Hilfetext-Beispiel `start requirement` wird live mit 400 abgelehnt (nur PascalCase gültig) |
| AUD-2026-09-114 | **High** | NEU | — | `…/__tests__/api.test.ts:8-9,31,42-43,62-63`; `…/tests/test_slash_command.py:40` | 210 grüne Tests, zwei Live-Bugs: Fixtures kodieren einen Vertrag, den der Server nicht erfüllt |
| AUD-2026-09-117 | **High** | NEU | — | `…/src/state.ts:196-198` + `ConnectedView.tsx:6-24` | MCP-Fehler wird nie angezeigt — `interviewError` nur in Views gerendert, die `view==="connected"` nicht baut |
| AUD-2026-09-102 | Medium | NEU | — | `…/hermes-plugin.json:16` vs `src/activate.ts:60-75` | Deklarierte `contributes.commands`/`statusBarItems.command` werden nie registriert |
| AUD-2026-09-111 | Medium | NEU | — | `integrations/hermes-agent-plugin/__init__.py:138` | `formalize` gibt rohes Response-Dict aus statt der Artefakt-ID (`artifact_id` existiert nicht) |
| AUD-2026-09-112 | Medium | NEU | — | `integrations/hermes-agent-plugin/reqogniloom_client.py:54-60,197-204` | `/interviews/` hat kein `count` → `open interviews` dauerhaft `None`, ohne Diagnose |
| AUD-2026-09-113 | Medium | NEU | — | `dist/plugins/*/reqogniloom/skills/interview-management/SKILL.md` + `dist/plugins/claude-code/reqogniloom/agents/*.md` | Mitgelieferter Skill ist unbenutzbar: alle 10 `interview.*`-Tools außerhalb jeder Rollen-Whitelist |
| AUD-2026-09-118 | Medium | NEU | — | `…/src/state.ts:157-158` (+ `:101-118`) | API-Key wird im Klartext in den Host-Storage geschrieben und ohne Ablauf wiederhergestellt |
| AUD-2026-09-106 | Medium | NEU | — | `integrations/hermes-agent-plugin/plugin.yaml:2`; `dashboard/manifest.json:6` | Python-Plugin-Version `0.1.0` statt `VERSION`; von `build_hermes_plugin.py` nicht erfasst |
| AUD-2026-09-107 | Medium | BESTAETIGT | CR-21 (Klasse) | `backend/mcp_server/protocol_handler.py:505`; `backend/mcp_server/views.py:431` | MCP `serverInfo.version` hart `1.0.0`, unabhängig von `VERSION` (live bestätigt) |
| AUD-2026-09-103 | Low | NEU | — | `…/hermes-plugin.json:40-46` | `engines.hermes` und `permissions` werden von keinem Code gelesen — dekorativ |
| AUD-2026-09-104 | Low | NEU | — | `…/hermes-plugin.json` (gesamtes Dokument) | Kein `capabilities`/`tools`/`minHostVersion`-Feld; deklarierte Oberfläche nur im Quelltext |
| AUD-2026-09-105 | Low | NEU | — | `…/hermes-plugin.json` (kein `auth`-Feld) | Keine Auth-Spezifikation im Manifest; Tokenquelle rein implizit (UI-Formular) |
| AUD-2026-09-108 | Low | NEU | — | `backend/reqogniloom/version.py:78-105` | `GET /api/v1/version/` liefert live `{"app_version":"unknown"}` — Version zur Laufzeit nicht verifizierbar |
| AUD-2026-09-116 | Low | NEU | — | `…/src/state.ts:140`; `api.ts:113` | Timeout (exakt 15005 ms) und Connection-Refused ergeben dieselbe Meldung „Connection failed."; keine Diagnose, kein Log |
| AUD-2026-09-119 | Low | NEU | — | `integrations/hermes-agent-plugin/reqogniloom_client.py:95` vs `docs/agent-templates/INSTALL.md:130-158` | Undokumentierte zweite Auth-Konvention (`Bearer reqlo_…`) neben `X-API-Key` |
| AUD-2026-09-150 | Info | BESTAETIGT | CR-25 | `deploy/docker-compose.yml:1325`; `.env.example:511,515` | Bluepencil registriert + Sidecar läuft gesund; es fehlt **nur** `VITE_BLUEPENCIL_ENABLED=1` |
| AUD-2026-09-151 | Info | BESTAETIGT | CR-25 | `deploy/bluepencil` (live `/notes`) | `GET /bluepencil/api/notes` liefert ohne Credential 200 mit Notizen aller Workspaces |
| AUD-2026-09-152 | Info | WIDERLEGT | CR-24 | `integrations/hermes-plugin/`, `integrations/hermes-agent-plugin/` | „nicht live verifizierte Verträge" ist überholt — beide **sind** live verifizierbar; je einer bricht |
| AUD-2026-09-153 | Info | NEU | — | `dist/plugins/hermes/` | Verzeichnis enthält nur Builder + Test, kein Plugin-Artefakt; im Repo nirgends aufgelöst |

> **ID-Hinweis:** Die ursprünglich für die vier Info-Findings vergebenen IDs
> 120–123 kollidierten mit `AUDIT_INFRASTRUCTURE.md` (WP-1c, parallel entstanden,
> Bereich 120–149). Sie wurden deshalb auf **150–153** umnummeriert. Der Bereich
> **100–119** ist unstreitig.

### Verteilung

| Schweregrad | Anzahl | IDs |
|---|---|---|
| Critical | 1 | 115 |
| High | 6 | 100, 101, 109, 110, 114, 117 |
| Medium | 7 | 102, 106, 107, 111, 112, 113, 118 |
| Low | 6 | 103, 104, 105, 108, 116, 119 |
| Info | 4 | 150, 151, 152, 153 |
| **Gesamt** | **24** | |

| Klassifikation | Anzahl | IDs |
|---|---|---|
| NEU | 20 | 100, 101, 102, 103, 104, 105, 106, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 153 |
| BESTAETIGT | 3 | 107 (CR-21), 150 (CR-25), 151 (CR-25) |
| WIDERLEGT | 1 | 152 (CR-24) |
| DUPLIKAT | 0 | — |
| BLOCKED | 0 Findings | 10 offene Fragen (Evidenz 1 §6, Evidenz 3 §9) |
| **Gesamt** | **24** | |

**Kein einziges Finding ist ein DUPLIKAT.** Zusätzlich wurde **CR-22** auf
Track-Ebene als Precision-Update verbucht (dort *WIDERLEGT*, siehe §6) — ohne neues
Finding, weil der Punkt bereits erfasst war.

**Kein einziges Finding ist ein DUPLIKAT** — die WP-1-Track-Liste wurde gegen jeden
Kandidaten geprüft (issue-inventory.md:110 „Plugin/Hermes/Bluepencil" mit #456, #545,
#599, #649, #683, #867, #946, #980, #981, #988, #1031, #1086–#1094). **Keines dieser
20 offenen/geschlossenen Issues beschreibt einen der hier gefundenen Defekte.** Die
6 offenen (#649, #988, #1087, #1089, #1094 + die Nicht-Plugin-Serie) sind andere
Themen. Vor jeder `NEU`-Vergabe wurde gegengeprüft.

---

## 4. Top 5

| # | ID | Ort | Ein-Satz-Auswirkung |
|---|---|---|---|
| 1 | **AUD-2026-09-115** | `integrations/hermes-agent-plugin/__init__.py:79` | Der `/reqogniloom`-Slash-Command wirft bei `start`, `status` und `answer` einen `TypeError` aus dem Host heraus — die drei Kernbefehle des Plugins sind live unbenutzbar, während 106 Tests grün sind. |
| 2 | **AUD-2026-09-109** | `…/src/api.ts:143-153` + `reqogniloom_client.py:136-139` | Beide Plugins ignorieren die DRF-Paginierung und zeigen nur die ersten 25 von 401 Workspaces — der eigentliche Demo-Workspace `4eee7ca1-…` ist über die Plugin-UI nicht auswählbar. |
| 3 | **AUD-2026-09-110** | `integrations/hermes-agent-plugin/__init__.py:62,105-107` | Der im Hilfetext wörtlich angebotene Aufruf `start requirement` wird live mit `400 VALIDATION_ERROR` abgelehnt; nur PascalCase funktioniert, der Client normalisiert nichts. |
| 4 | **AUD-2026-09-117** | `…/src/state.ts:196-198` + `ConnectedView.tsx` | Schlägt ein MCP-Aufruf fehl, bleibt das Panel auf „Connected" ohne jede Fehlermeldung — der Nutzer klickt „Interviews" und es passiert scheinbar nichts. |
| 5 | **AUD-2026-09-114** | `…/__tests__/api.test.ts:8-9` + `tests/test_slash_command.py:40` | 210 grüne Tests (106 Py + 104 TS) verdecken zwei Live-Bugs, weil die Fixtures `next: null` bzw. `missing_fields: ["title"]` vorgeben, der Server aber `next: "?page=2"` bzw. `[{…}]` liefert. |

---

## 5. Warum der Merge `abd61aed` (PR #1118) **nicht vollständig** war

Der Merge hat **sechs** Hunde-Escape-Bugs in genau dieser Datei geschlossen
(`reqogniloom_client.py` Read-Timeout, `list_workspaces`-`.get()` vor dem
`isinstance`-Guard, fehlender Key als 200er-Null-Payload, Seitenlänge als Gesamtzahl,
`async def`-Handler auf der Event-Loop, `workspaces[0]["id"]`-KeyError). Dasselbe
Fehlermuster — eine Exception entweicht dem Fehlervertrag — ist an einer Stelle
**übrig geblieben**:

* `__init__.py:87-88` verspricht ausdrücklich *„Never raises — every error path returns
  a human-readable string instead."*
* `__init__.py:79` wirft bei `', '.join(missing)` einen `TypeError`, weil
  `missing_fields` serverseitig eine Liste von **Dicts** ist.
* `except ReqogniLoomError` (`:162`) fängt `TypeError` nicht.

Live reproduziert für `start`, `status` **und** `answer` (Evidenz 2 §6). Zusätzlich
sind zwei der sechs gefixten Fehler nur halb gefixt:

| PR-#1118-Fix | Status nach Live-Prüfung |
|---|---|
| Read-Timeout entwich `_request` | ✔ behoben |
| `list_workspaces` `.get()` vor `isinstance` | ✔ behoben |
| Fehlender Key → 200er-Null-Payload | ✔ behoben (`_AuthError`) |
| Seitenlänge als Gesamtzahl gemeldet | ⚠️ **halb** — auf `count` umgestellt, aber `/interviews/` hat kein `count` → `open interviews: None` (112) |
| `async def` auf Event-Loop | ✔ behoben |
| `workspaces[0]["id"]` KeyError | ✔ behoben |
| **„Never raises"** | ✘ **nicht behoben** (115) |

→ **AUD-2026-09-115 ist ein `NEU`-Finding, kein `BESTAETIGT`:** Das Issue-Bundle hat
keine Issue-Nummer, die genau diese Restlücke beschreibt (der Commit nennt in seinem
Text keine Issue-Nummern außer der PR-#1118). Die verwandte Vorab-Track **CR-24**
(„Hermes-TS und Python-Agent-Plugin sind parallele, nicht live verifizierte
Verträge") ist durch diese Prüfung **überholt** → 152 WIDERLEGT.

---

## 6. Reconciliation mit den Vorab-Tracks

| Track | Vorab-Aussage | WP-2-Befund | Klassifikation |
|---|---|---|---|
| **CR-21** | „MCP-Dokumentation, Agent-Prompts, Version driften; Stdio nicht geroutet" | **Plugin-seitiger Versions-Sync ist PASS** (alle Manifeste == `VERSION`). Die Versions-Drift existiert nur außerhalb der Plugins: hartkodierte `serverInfo.version: "1.0.0"` (live bestätigt) | **BESTAETIGT** (107), Klasse und Ort präzisiert |
| **CR-22** | „Plugin-Header sind dekorativ; HTTP/SSE-Batchverträge und Hermes-Timeouts divergieren; Header sind keine Scope-Quelle" (belegt u. a. mit `mcpClient.ts:52-70`) | **Präzisierung**: der dekorative Header ist `X-API-Key` nicht — er **ist** die Scope-Quelle. Live bewiesen: `X-API-Key: reqlo_…` → 80 Read-Tools, `reqlo_…` mit Scope `readwrite` → 403. Der `X-API-Key`-Header des Hermes-TS-Plugins wird real ausgewertet. Der Timeout-Divergenz-Teil ist **widerlegt**: `REQUEST_TIMEOUT_MS = 15_000` in `api.ts:113` und `mcpClient.ts:60` sind identisch und greifen live exakt bei 15005 ms | **WIDERLEGT** (Track-Precision, kein neues Finding) |
| **CR-23** | „Plugin-Allow/Blocklisten sind Prompt-Governance" | bestätigt strukturell: die Claude-Code-Whitelists sind clientseitig; serverseitig entscheidet `scope`+RBAC. Konkret quantifiziert: 45 **Read-only**-Tools sind über keine Rolle aufrufbar (113) | Teil von **113** |
| **CR-24** | „Hermes-TS und Python-Agent-Plugin sind parallele, nicht live verifizierte Verträge; CI priorisiert nur TS" | **WIDERLEGT** im Kern: beide sind live verifizierbar und wurden verifiziert. **Parallel bleiben sie** — aber nicht gleich kaputt: TS funktioniert, Python crasht im Hauptpfad (115) und folgt einer zweiten Auth-Konvention (119) | **WIDERLEGT** (122) |
| **CR-25** | „Bluepencil ist standardmäßig deaktiviertes Debug/QS-Profil; bei Aktivierung fehlen AuthN/Tenant-Isolation" | **Voll bestätigt, beides gemessen.** Default-off: `.env.example:515 BLUEPENCIL_ENABLED=0`. Sidecar **läuft trotzdem** (`Up 7 hours (healthy)`, `/health` → 200) und ist nur compose-intern erreichbar (kein Host-Port). `GET /bluepencil/api/notes` → **200 ohne jede Credential** | **BESTAETIGT** (150, 151) |
| **CR-27** | Auth-Policy-Lücken im Backend | außerhalb WP-2-Scope, nicht erneut geprüft | — (nicht berührt) |
| **CR-28** | „MCP-Session-ID ist ein URL-Bearer-Credential mit 8-h-TTL" | **live bestätigt**: `data: /mcp/messages/?session_id=fb8fab7a-…` — die Session-ID steht im Query-String und damit in jedem Proxy-/Access-Log. Genau die Transportform, die `.mcp.json:5` und `mcp_config.json:4` konfigurieren | **BESTAETIGT**, kein neues Finding (bereits erfasst) |

---

## 7. Was gut war (explizit)

* **Null Über-Deklaration** in allen `dist/`-Paketen: 80/80 Agent-Tools, 82/82
  Skill-Text-Referenzen und 129/129 `skills-tool-refs.json`-Referenzen existieren in
  der 219er-Registry. Kein Phantom, kein toter Whitelist-Eintrag.
* **`/mcp/sse/` ist kein Phantom** (anders als `/mcp/stdio/` laut WP-1a): vollständiger
  SSE-Handshake live gefahren — `event: endpoint` mit `session_id`, `POST
  /mcp/messages/?session_id=…` → `202`, gefälschte Session → `401`.
* **Fehlerübersetzung im Hermes-TS-Plugin ist gut**: 401/403/Timeout werden
  plugin-spezifisch übersetzt, nested **und** flache Fehler-Hülle werden verstanden
  (`api.ts:23-59`), kein Stacktrace-Leak, kein Key im Log.
* **Die `dist`-Konvention ist sauber**: `${REQOGNILOOM_MCP_URL}` /
  `${REQOGNILOOM_API_KEY}` + `X-API-Key`, von `dist/test_mcp_convention_parity.py`
  gepinnt, kein Literal-Key in einer ausgelieferten Datei.
* **Der Dashboard-Auth-Guard ist das einzige fail-closed-Gate im Bestand**
  (`plugin_api.py:130-146`, Router-Dependency **und** Handler-Check,
  `secrets.compare_digest`, Origin- **und** Host-Allowlist mit Loopback-Default) —
  vorbildlich.
* **Kein RCE, kein Drittanbieter-Egress**: 0× `eval`/`new Function`/`shell=True`/
  `os.system`/`pickle`; `subprocess` nur in Build-Tests mit fester Argumentliste; das
  komplette Netlog des Erfolgslaufs besteht aus 5 Requests, alle gegen den
  konfigurierten `baseUrl`.
* **Der Build-Guard ist echt**: `scripts/verify-build.mjs` lädt das gebaute Bundle als
  ES-Modul, ruft `register(ctx)` und prüft Panel-Registrierung — und meldet
  verbotene Tokens (`process`, `__hermesPlugins`, inline `jsx-runtime`).
* **PR `#1118` hat die `FORMALIZABLE_ARTIFACT_TYPES`-Schranke wirklich entfernt** —
  alle 8 Start-Buttons waren live `enabled=true`.

---

## 8. Empfohlene Reihenfolge (rein priorisierend, keine Umsetzung)

1. **115** — `_fmt_state` typisieren; die beiden Test-Fixtures auf den echten
   Vertrag nachziehen. Einzeiler-Fix, höchste Wirkung.
2. **109 + 112** — Paginierung in beiden Clients; `count` für `/interviews/`
   nachliefern oder den Zähler als „nicht verfügbar" markieren.
3. **110 + 111** — `artifact_type` auf die kanonische Form normalisieren und den
   Hilfetext korrigieren; `formalize` auf `resulting_artifact_ids` ausrichten.
4. **117** — `interviewError` auch in `ConnectedView` rendern.
5. **100 + 101** — Hermes-Installationsabschnitt in `INSTALL.md` und ein
   Versions-/SDK-Mindestvertrags-Gate, das fail-closed ist.
6. **114** — Fixture-Wächter, der Mock-Payloads gegen die Live-Antwort prüft, damit
   210 grüne Tests nicht weiter Live-Bugs verdecken.
7. **118** — Ablauf/Nutzerhinweis für die Key-Persistenz; Host-Storage-Verhalten
   dokumentieren (die Host-Frage bleibt BLOCKED).
8. **113** — entweder `interview.*` in eine Rolle aufnehmen oder
   `interview-management` aus den Claude-Code-/Antigravity-Paketen entfernen.

---

## 9. Methodische Grenzen dieses Audits

* Alle Plugin-Aussagen beruhen auf **real ausgeführten** Requests oder auf
  `datei:zeile`-Belegen. Kein Finding beruht auf einem Manifest-Lesen allein.
* Fünf Host-seitige Fragen bleiben **BLOCKED** (Evidenz 1 §6, Evidenz 3 §9): Hermes,
  Claude Code und Antigravity sind auf diesem Host nicht installiert. Betroffen sind
  Aussagen über *Client-Verhalten*, nicht über die Plugins selbst.
* `GET /api/v1/version/` liefert live `"unknown"`, d. h. der laufende Stack kann seine
  eigene Version nicht belegen (108). Alle Versionsaussagen dieses Berichts stammen
  deshalb aus dem Repo-Stand `3dcc80d8`, nicht aus der laufenden Instanz.
* Die lokale pytest-Ausführung benötigt `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, weil ein
  global installiertes `pytest-homeassistant-custom-component` unter Windows an
  `fcntl` scheitert. Das ist eine Umgebungs-, kein Produkt-Eigenschaft; die
  relevanten Suiten liefen unter dieser Einstellung grün (106 + 104).
