---
adr_id: ADR-017
title: "`VERSION` ist SSOT der Server-Version; Plugin-Versionierung ist Nicht-Produkt-Zusage (Dritt-/POC-Plugins führen eigene SemVer mit minServerVersion)"
status: accepted
date: "2026-10-03"
deciders: [user, senior-developer]
affected_reqs: [REQ-L1-005, REQ-L1-006, REQ-L1-082, REQ-L2-MC-016, REQ-L2-MC-019]
superseded_by: null
---

# ADR-017: `VERSION` ist SSOT der Server-Version; Plugin-Versionierung ist Nicht-Produkt-Zusage (Dritt-/POC-Plugins führen eigene SemVer mit `minServerVersion`)

**Status:** accepted (2026-10-03) — User-Freigabe nach `concept-reviewer`-Review (RVW-2026-10-03-004, Iteration 2: APPROVED).
**Datum:** 2026-10-03
**Entscheider (vorgeschlagen):** user, senior-developer
**Betroffene REQs:** REQ-L1-005 (MCP Server mit vollständigem Read/Write-Zugriff,
`docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md:119`), REQ-L1-006 (Synchrone
maschinenlesbare API mit Spezifikation, ebd. `:143`), REQ-L1-082 (Global System
Announcement, ebd. `:860`), REQ-L2-MC-016 (System Info Tool (Announcement),
`docs/se/L1/Gesamtsystem/L2/McpServerSystem/L2_McpServerSystem_Requirements.md:188`),
REQ-L2-MC-019 (MCP Protocol Compliance & Schemas, ebd. `:238`)

**Bezug:** Audit-Kandidat **#7** (`docs/audit/2026-09/AUDIT_ADR_CANDIDATES.md:320-370`),
Implementation-Plan-Slot **ADR vii** (`docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md:226`),
Arbeitseinheit `PLUG-04` (`docs/audit/2026-09/review/plan/PLUGINS.md:58-70`). Findings
`AUD-2026-09-100`, `-101`, `-106`, `-107`, `-108`, `-102`–`-105`, `-119`.

**Bezug zum Code:** `VERSION` = `1.8.0-beta.17` (Repo-Wurzel);
`backend/mcp_server/protocol_handler.py:503-506` (`serverInfo.version` **hart `"1.0.0"`**);
`backend/mcp_server/views.py:482` (`"version": "1.0.0"` in der Discovery-Antwort);
`backend/reqogniloom/version.py:74-103` (`_resolve_app_version`: `APP_VERSION`-Env →
`VERSION`-Datei → `"unknown"`) und `:106-136` (`VersionView`, `GET /api/v1/version/`);
`integrations/hermes-agent-plugin/plugin.yaml:2` (`version: 0.1.0`),
`integrations/hermes-agent-plugin/dashboard/manifest.json:6` (`"version": "0.1.0"`);
`integrations/hermes-plugin/reqogniloom/hermes-plugin.json:4` (`"version":
"1.8.0-beta.17"`), `:40-46` (`engines.hermes`, `permissions` — heute dekorativ).

**Review-/Lifecycle-Vermerk:** Dieses ADR ist **`accepted`**. Es wurde als begründete
**Empfehlung** formuliert und nach Review durch den User freigegeben. Die abhängige
Umsetzung (`PLUG-04`) beginnt **nach** der Freigabe.
**Review-Iteration 1** (`RVW-2026-10-03-001`): Verdict CHANGES_REQUESTED; die
major-Befunde `002-01`/`002-02` sowie die minors `002-03`–`002-05` wurden eingearbeitet.
**Review-Iteration 2** (`RVW-2026-10-03-004`): Verdict APPROVED; keine critical/major offen.
**Statuswechsel 2026-10-03:** `proposed → accepted` auf User-Entscheid nach Iteration 2 (RVW-2026-10-03-004, alle drei APPROVED). Grund: Inhaltlich reif, keine critical/major offen; Restpunkte sind info/minor und blockieren nicht. Prozess-Finding 000-01 (Erstellung durch `senior-developer` statt `se-architect`) wird als dokumentierte, vom User getragene Abweichung festgehalten — kein Blocker.

---

## Kontext

**1. Es gibt nicht „eine" Version, sondern mehrere widersprüchliche Orte.**

| Ort | gemessener Wert | Fundstelle |
|---|---|---|
| Projektversion | `1.8.0-beta.17` | `VERSION` (Repo-Wurzel) |
| MCP `serverInfo.version` | **hart `1.0.0`** | `mcp_server/protocol_handler.py:503-506` |
| MCP-Discovery (`GET /mcp/`) | **hart `1.0.0`** | `mcp_server/views.py:482` |
| `GET /api/v1/version/` | `APP_VERSION` → `VERSION`-Datei → `unknown` | `reqogniloom/version.py:74-136` |
| Python-Hermes-POC-Plugin | `0.1.0` | `integrations/hermes-agent-plugin/plugin.yaml:2` |
| Python-POC-Dashboard-Manifest | `0.1.0` | `integrations/hermes-agent-plugin/dashboard/manifest.json:6` |
| TS-Hermes-Plugin | `1.8.0-beta.17` | `integrations/hermes-plugin/reqogniloom/hermes-plugin.json:4` |
| Build-Artefakt `dist/plugins/**` | generiert | Build-Skripte `dist/plugins/*/build_*_plugin.py` |

Solange „welche Version gilt" nicht entschieden ist, kann **keine**
Kompatibilitätszusage zwischen Plugin, Server und Doku geprüft werden
(`AUDIT_ADR_CANDIDATES.md:342-343`).

**2. Zwei verschiedene Versions-Begriffe werden vermischt.** Eine **Server-/Applikations-
version** (die laufende ReqogniLoom-Instanz) ist etwas anderes als eine **Plugin-Version**
(ein installierbares Artefakt, das gegen einen Host/eine Server-API läuft). Die
Kopplungsfrage lautet: Muss ein mitgeliefertes Plugin dieselbe Zahl tragen wie der Server
(weil sie gemeinsam released werden), oder darf es unabhängig semverisiert werden (weil
der Host es unabhängig installiert/updated)?

**3. Der Server hartkodiert seine Version.** `protocol_handler.py:505` und `views.py:482`
liefern `1.0.0` — unabhängig von `VERSION`. Gleichzeitig ist `version.py` bereits
korrekt gebaut: es liest `APP_VERSION` (Build-Stempel) mit `VERSION`-Datei als Fallback
(`version.py:89-101`). Die Lücke ist damit **lokal** (MCP-Pfad), nicht strukturell.

**4. Der MCP-Vertrag verlangt `serverInfo`.** `REQ-L2-MC-019` fordert
Protokoll-Compliance; `initialize`/`serverInfo` ist Teil davon. `REQ-L1-005`/`REQ-L1-006`
sind die übergeordneten MCP-/REST-Zusagen. `REQ-L2-MC-016`/`REQ-L1-082` betreffen
System-Info-Aussagen an Agenten. **Kein REQ regelt jedoch die Plugin-Versionierung
selbst** — das ist ein realer Zuordnungs-Gap und wird unten als offener Punkt geführt
(nicht geraten).

**Konsequenz für den Scope (Befund 002-02):** Die produktive, REQ-verankerte
Entscheidung dieses ADR betrifft ausschließlich die **Server-/Protokoll-Version** (durch
`REQ-L1-005`/`-006`/`-082`, `REQ-L2-MC-016`/`-019` gedeckt). Die **Plugin-Versionierung**
— inklusive der im Repo mitgelieferten Bundle-Manifeste und des Python-POC-Plugins — ist
mangels REQ-Anker **Nicht-Produkt-Zusage**: sie wird als Mechanismus benannt und der
zuständigen Rolle überlassen, aber **nicht** als Produktversprechen in der Kaskade
verankert. Es wird **keine** REQ erfunden (s. Offene Punkte).

**5. Das Manifest ist teils dekorativ.** `hermes-plugin.json:40-46` deklariert
`engines.hermes`/`permissions`, die laut Audit keine Durchsetzung haben; `-101` stellt
fest, dass das Manifest ein VS-Code-Schema, nicht der Hermes-Vertrag ist. Eine
Versions-Entscheidung ist damit Teil der Klärung, **welche** Felder überhaupt Vertrag sind.

**Threat-Model (4 Fragen, Versions-Exposition & Dritt-Plugin-Vertrag):**

1. *Was gebaut?* Versions-Exposition via MCP `serverInfo` + öffentliche
   `/api/v1/version/`; Build-Generierung der im Repo erzeugten Manifeste;
   Kompatibilitätsfeld für Dritt-Plugins.
2. *Was schiefgeht?* Versions-Disclosure erleichtert CVE-Korrelation (bereits durch den
   gekürzten SHA entschärft, `version.py:114-122`); eine falsche oder erzwungene
   Kompatibilitätsangabe eines Dritt-Plugins kann Clients brechen.
3. *Gegenmaßnahme?* Reale Version aus `VERSION`, gekürzter SHA bleibt; das
   Kompatibilitätsfeld ist nur dann Vertrag, wenn es validiert wird — sonst wird es
   entfernt (Entscheidung 4).
4. *Konsequenz?* Geringe Recon-Fläche; Fehl-Kompatibilitätszusagen sind ein Host-Risiko.

---

## Alternativen

### Option A: `VERSION` ist SSOT — Serverversion speist MCP und REST; mitgelieferte Manifeste werden beim Build daraus erzeugt — GEWÄHLT (Empfehlung)

**Beschreibung:** `VERSION` (bzw. der Build-Stempel `APP_VERSION`) ist die **eine**
Serverversion. `serverInfo.version`, die Discovery-Antwort und `/api/v1/version/` werden
daraus gespeist. Die **erstanbieter-, im Repo gebauten** Plugin-Manifeste (`dist/plugins/**`,
`hermes-plugin`) werden beim Build aus `VERSION` befüllt und sind nicht editierbar. Für
**externe/dritte** Plugins gilt ergänzend der B-Vertrag (`minServerVersion`).

**Abwägung:** Eine Zahl, überall identisch; Abnahme und Doku werden prüfbar. Der Task
`PLUG-04` nennt als Akzeptanz ausdrücklich „`serverInfo.version` == `VERSION`". Die
Server-Hartkodierung ist die konkrete Ursache von `-107` und wird mit A beseitigt.
Gleichzeitig bleibt A ehrlich: Es behauptet **nicht**, dass fremde Plugins dieselbe Zahl
tragen müssen — dafür dient das Kompatibilitätsfeld.

**Risiko:** NIEDRIG — lokal im MCP-Pfad, mit Build-Generierung gut testbar. Laufende
Clients, die auf `1.0.0` geprüft haben, sehen erstmals die reale Version (das ist die
gewünschte Korrektur, keine Regression).

### Option B: Unabhängige Plugin-SemVer — verworfen **als alleiniges Modell** (Bausteine als Ergänzung übernommen)

**Beschreibung:** Jedes Plugin trägt seine **eigene** SemVer; ein `minServerVersion`-Feld
erklärt die Beziehung.

**Abwägung:** Verworfen ist **B als alleiniges Modell**. Die widersprüchlichen
Server-Orte (`1.0.0` vs. `VERSION`) blieben damit unentschieden, und die im Repo
mitgelieferten Artefakte (`1.8.0-beta.17` vs. `0.1.0`) drifteten weiter. Der
B-Baustein `minServerVersion` wird jedoch **als Ergänzung** für Dritt-/POC-Plugins in
Option A übernommen (Entscheidung 3).

**Risiko:** MITTEL — erzeugt Pflegeaufwand, ohne den akuten Server-Defekt zu schließen.

### Option C: Build-Artefakt als Wahrheit — VERWORFEN

**Beschreibung:** Was der Host installiert, ist die Wahrheit; Versionsangaben entstehen
beim Build und sind nicht editierbar.

**Abwägung:** Deckt sich mit A für die im Repo gebauten Artefakte, ist aber als
**alleinige** Antwort zu schwach: Debugging jenseits des installierten Stands wird
unmöglich, und die Server-/Protokollversion (MCP `serverInfo`) ist kein Plugin-Artefakt.
C ist ein **Mechanismus** von A, keine eigene Achse.

**Risiko:** MITTEL — zu enger Begriff der „Version".

### Teilfrage: Eigene `serverInfo`-SemVer vs. Spiegelung der Projektversion

- **Spiegelung (in A):** `serverInfo.version == VERSION`. Einfach, prüfbar, entspricht
  dem Akzeptanzkriterium von `PLUG-04`.
- **Eigene SemVer:** Nur sinnvoll, wenn das MCP-Protokoll unabhängig vom Produkt
  versioniert würde — heute nicht der Fall; `protocolVersion` ist bereits ein **eigenes**
  Feld (`protocol_handler.py:499`) und trägt die Protokollversion. Die Produktversion
  gehört daher in `serverInfo.version`, nicht in ein weiteres Versionsschema.

**Empfehlung: Spiegelung.**

---

## Entscheidung

**Empfehlung: Option A für die Server-Version, B-Baustein (`minServerVersion`) als
Ergänzung für Dritt-/POC-Plugins. Die Plugin-Versionierung selbst ist
Nicht-Produkt-Zusage (Scope-Abgrenzung, s. Kontext 4).**

1. **`VERSION` ist die SSOT der Server-Version (Produkt, REQ-verankert).**
   `serverInfo.version` (`mcp_server/protocol_handler.py:505`) und die
   Discovery-Antwort (`mcp_server/views.py:482`) werden **nicht** mehr hartkodiert,
   sondern aus derselben Auflösung gespeist, die `version.py:74-103` bereits
   bereitstellt (`APP_VERSION`-Stempel → `VERSION`-Datei → `unknown`).
   `/api/v1/version/` bleibt die öffentliche, nicht sensible Quelle (Version +
   gekürzter Commit). Akzeptanz: `serverInfo.version == VERSION`.
2. **Python-POC-Plugin: eigenständig versioniert (entweder/oder aufgelöst).** Das
   POC-Artefakt `integrations/hermes-agent-plugin` (`plugin.yaml:2`, `0.1.0`) ist
   **nicht** Teil des Produkt-Release-Zyklus und wird **explizit als eigenständiges,
   unabhängig semverisiertes POC-Artefakt deklariert**, das ein `minServerVersion`
   deklariert. Die Alternative — das POC-Plugin auf Build-Generierung aus `VERSION`
   umzustellen — ist damit **verworfen** (sie würde ein Nicht-Produkt-Artefakt in den
   Produkt-Release-Zyklus ziehen, für den es keinen REQ-Anker gibt). Die im Repo
   **produktiv** ausgelieferten Bundle-Manifeste (`dist/plugins/**`, TS-Hermes-Plugin)
   werden weiterhin beim Build aus `VERSION` erzeugt; ihre Versionsangabe ist damit
   nicht manuell pflegbar und kann nicht driften.
3. **Kanonisches Kompatibilitätsfeld ist genau eines: `minServerVersion`.** Externe/und
   POC-Plugins deklarieren **ein** Feld, `minServerVersion` (Minimum-SemVer des Hosts),
   das der Host beim Laden prüft. Das heute dekorative `engines.hermes`
   (`hermes-plugin.json:40-46`) wird durch `minServerVersion` **ersetzt** oder
   entfernt; es ist **kein** zweiter Vertrag. Schema und Validierung sind Teil von
   `PLUG-04`. Damit ist eindeutig, welches Feld verbindlich ist.
4. **Durchsetzung statt Dekor.** `minServerVersion` bleibt nur Vertrag, wenn der Host
   es tatsächlich prüft (Schema-Validierung + Kompatibilitäts-Check beim Laden);
   `permissions`/`engines.hermes` werden entfernt, solange keine Durchsetzung existiert
   (`-101`). Als reine Anzeige deklarierte Felder sind aus dem Manifest zu entfernen.
5. **Kaskade:** `PLUG-04` implementiert `serverInfo`-/`/version/`-Parität und (soweit
   produktiv) die Build-Generierung; Akzeptanz „`serverInfo.version` == `VERSION`".
   Die POC-Plugin-Deklaration (Punkt 2) ist **kein** `PLUG-04`-Akzeptanzkriterium,
   sondern eine Nicht-Produkt-Notiz.
6. **Scope-Abgrenzung / Traceability-Gap (Befund 002-02):** Es existiert **keine** REQ,
   die die Plugin-Versionierung selbst regelt. Die Plugin-Hälfte wird daher **nicht** als
   Produktentscheidung geführt (keine erfundene REQ); die herangezogenen REQs
   (`REQ-L1-005`/`-006`/`-082`, `REQ-L2-MC-016`/`-019`) belegen **nur** die
   Server-/MCP-Zusagen. Die Plugin-Versionierung bleibt ein **offener
   Traceability-Gap**, bis `requirements` entweder eine REQ anlegt oder sie bewusst als
   Nicht-Produkt ausschließt (s. Offene Punkte).

---

## Konsequenzen

**Positiv:**

- `serverInfo.version` und `/api/v1/version/` werden **prüfbar** gegen `VERSION`; die
  widersprüchlichen Literale (`1.0.0`, `unknown`) verschwinden.
- Im Repo gebaute Plugin-Manifeste können nicht mehr driften (Build-Generierung).
- Ein Versionsbegriff für den Server, ein Kompatibilitätsfeld für Dritt-Plugins — die
  Vermischung wird aufgelöst.
- `PLUG-04` erhält eine prüfbare Akzeptanz; die `RELEASE_*`-Carrier-Konsistenz (bereits
  gelebte Praxis, siehe `docs/se/reports/RELEASE_v1.8.0-beta.17.md`) wird auf den
  MCP-Pfad ausgedehnt.

**Negativ:**

- **Laufende Clients, die `serverInfo.version == "1.0.0"` hart erwartet haben, sehen eine
  neue Zahl.** Das ist die gewünschte Korrektur, aber ein sichtbarer Wechsel und muss in
  der Doku benannt werden.
- **Python-POC-Plugin wird als eigenständig versioniert festgelegt** (`0.1.0`, eigene
  SemVer + `minServerVersion`); das trennt es bewusst vom Produkt-Release-Ritual.
- **Kompatibilitätsmatrix für Dritt-Plugins** muss jemand pflegen — bewusst als
  Host-Vertrag ausgewiesen, nicht dem Produkt-Release zugeschlagen. Solange
  `minServerVersion` nicht validiert wird, ist es dekorativ und daher zu entfernen.
- **`engines.hermes`/`permissions` bleiben unecht,** solange keine Validierung existiert;
  A entfernt sie andernfalls nur kosmetisch, nicht semantisch.
- **Plugin-Versionierung bleibt ein Traceability-Gap:** Ohne REQ-Anker kann die
  Kaskade die Plugin-Hälfte nicht prüfen; das ist bewusst als Nicht-Produkt-Zusage
  ausgewiesen, nicht stillschweigend verankert.
- **Freigabe erteilt (2026-10-03):** Status `accepted`; die abhängige `PLUG-04`-Umsetzung
  startet nach der User-Freigabe.

---

## Offene Punkte

1. **Freigabe:** ✅ erledigt — Statuswechsel `proposed → accepted` am 2026-10-03 durch den User nach `concept-reviewer`-Review (RVW-2026-10-03-004, Iteration 2 APPROVED).
2. **Traceability-Gap Plugin-Versionierung (Befund 002-02):** Es existiert **keine** REQ
   für die Plugin-Versionierung. Der ADR-Scope ist deshalb präzise auf die Server-Version
   begrenzt; die Plugin-Versionierung ist als **Nicht-Produkt-Zusage** ausgewiesen. Offen
   bleibt allein die Entscheidung von `requirements`, ob eine REQ (Integration/API) angelegt
   oder die Nicht-Produkt-Zusage dauerhaft festgeschrieben wird. **Keine** REQ wird in
   diesem ADR erfunden.
3. **`open_adrs`** (`AUD-2026-09-333`): maschinelle REQ↔ADR-Verknüpfung fehlt; keine
   REQ-Datei-Änderung in diesem ADR.
4. **`minServerVersion`-Schema/Validierung:** konkretes Format (Minimum-SemVer) und
   Ladeprüfung sind Teil von `PLUG-04`; ohne Validierung ist das Feld zu entfernen.
5. **`engines.hermes`/`permissions`:** nur bei tatsächlicher Validierung Vertrag, sonst
   entfernen (`-101`).

---

*Erstellt durch `senior-developer` am 2026-10-03; am 2026-10-03 nach Review
(`RVW-2026-10-03-004`, Iteration 2 APPROVED) durch den User auf `accepted` gesetzt.
Kein Produktcode, keine Migration, kein Push.*
