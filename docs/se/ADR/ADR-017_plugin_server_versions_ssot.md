---
adr_id: ADR-017
title: "`VERSION` ist SSOT der Serverversion; Plugin-Manifeste werden daraus generiert, externe Plugins führen eigene SemVer mit minServerVersion-Vertrag"
status: proposed
date: "2026-10-03"
deciders: [user, senior-developer]
affected_reqs: [REQ-L1-005, REQ-L1-006, REQ-L1-082, REQ-L2-MC-016, REQ-L2-MC-019]
superseded_by: null
---

# ADR-017: `VERSION` ist SSOT der Serverversion; Plugin-Manifeste werden daraus generiert, externe Plugins führen eigene SemVer mit `minServerVersion`-Vertrag

**Status:** proposed (Empfehlung — Freigabe durch User/Review offen)
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

**Review-/Lifecycle-Vermerk:** Dieses ADR ist **`proposed`**. Es formuliert eine
begründete **Empfehlung**, keine freigegebene Entscheidung. Die Freigabe erfolgt durch
den User nach Review (`concept-reviewer`); erst dann darf der Status wechseln. Die
abhängige Umsetzung (`PLUG-04`) beginnt **nach** der Freigabe.

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

**5. Das Manifest ist teils dekorativ.** `hermes-plugin.json:40-46` deklariert
`engines.hermes`/`permissions`, die laut Audit keine Durchsetzung haben; `-101` stellt
fest, dass das Manifest ein VS-Code-Schema, nicht der Hermes-Vertrag ist. Eine
Versions-Entscheidung ist damit Teil der Klärung, **welche** Felder überhaupt Vertrag sind.

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

### Option B: Unabhängige Plugin-SemVer — VERWORFEN (als alleiniges Modell)

**Beschreibung:** Jedes Plugin trägt seine **eigene** SemVer; ein `minServerVersion`-Feld
erklärt die Beziehung.

**Abwägung:** Korrekt für die **Host-Welt** und für **dritte** Plugins, aber als
alleiniges Modell löst es den gemessenen Ist-Zustand nicht: Die widersprüchlichen
Server-Orte (`1.0.0` vs. `VERSION`) bleiben unentschieden, und die im Repo mitgelieferten
Artefakte (`1.8.0-beta.17` vs. `0.1.0`) driften weiter. Es verlagert eine konkrete
Korrektur in eine Kompatibilitätsmatrix, die niemand pflegen will.

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

**Empfehlung: Option A mit B-Ergänzung für Dritt-Plugins.**

1. **`VERSION` ist die SSOT der Serverversion.** `serverInfo.version`
   (`mcp_server/protocol_handler.py:505`) und die Discovery-Antwort
   (`mcp_server/views.py:482`) werden **nicht** mehr hartkodiert, sondern aus derselben
   Auflösung gespeist, die `version.py:74-103` bereits bereitstellt (`APP_VERSION`-Stempel
   → `VERSION`-Datei → `unknown`). `/api/v1/version/` bleibt die öffentliche, nicht
   sensible Quelle (Version + gekürzter Commit).
2. **Mitgelieferte, im Repo gebaute Plugin-Manifeste sind Build-Artefakte.** `dist/plugins/**`
   und das TS-Hermes-Plugin werden beim Build aus `VERSION` befüllt; ihre
   Versionsangabe ist damit nicht manuell pflegbar und kann nicht driften. Das
   Python-POC-Plugin (`integrations/hermes-agent-plugin/plugin.yaml:2`, `0.1.0`) wird
   entweder auf die Build-Generierung umgestellt oder **explizit** als eigenständiges,
   unabhängig versioniertes POC-Artefakt deklariert (dann mit `minServerVersion`).
3. **Externe/dritte Plugins** dürfen eine **eigene** SemVer führen, müssen aber ein
   Kompatibilitätsfeld (`minServerVersion`, heute sinngemäß `engines.hermes`) deklarieren.
   Diese Matrix ist Teil des Host-Vertrags, nicht des Produkt-Release-Zyklus.
4. **`serverInfo`/Discovery-Doku werden ehrlich.** Der `engines.hermes`-Wert bleibt nur
   Vertrag, wenn er (z. B. durch den Build) tatsächlich durchgesetzt oder wenigstens
   validiert wird; andernfalls wird er als dekorativ entfernt (`-101`).
5. **Kaskade:** `PLUG-04` implementiert `serverInfo`-/`/version/`-Parität und die
   Build-Generierung; Akzeptanz „`serverInfo.version` == `VERSION`".
6. **Kein REQ-Fund für Plugin-Versionierung:** Es existiert **keine** REQ, die die
   Plugin-Versionierung selbst regelt. Das wird **nicht** geraten, sondern als offener
   Punkt (siehe unten) geführt; die herangezogenen REQs (`REQ-L1-005`/`-006`/`-082`,
   `REQ-L2-MC-016`/`-019`) belegen nur die betroffenen Server-/MCP-Zusagen.

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
- **Umstellung des Python-POC-Plugins** (`0.1.0`) auf Build-Generierung oder explizite
  Unabhängigkeit ist eine Entscheidung mit Folgen für dessen Release-Ritual.
- **Kompatibilitätsmatrix für Dritt-Plugins** muss jemand pflegen — bewusst als
  Host-Vertrag ausgewiesen, nicht dem Produkt-Release zugeschlagen.
- **`engines.hermes`/`permissions` bleiben unecht,** solange keine Validierung existiert;
  A entfernt sie andernfalls nur kosmetisch, nicht semantisch.
- **Entscheidung noch nicht freigegeben:** Status `proposed`; die abhängige `PLUG-04`-
  Umsetzung startet nach der User-Freigabe.

---

## Offene Punkte

1. **Freigabe:** `proposed → review → accepted` durch User nach `concept-reviewer`-Review.
2. **Fehlende REQ für Plugin-Versionierung:** Das ist ein **Dokumentations-/Traceability-
   Gap**, kein geratener Bezug. `requirements`/`DOC-01` sollten eine REQ (z. B. unter
   Integration/API) anlegen oder die Plugin-Versionierung bewusst als Nicht-Produkt-Zusage
   ausschließen.
3. **`open_adrs`** (`AUD-2026-09-333`): maschinelle REQ↔ADR-Verknüpfung fehlt; keine
   REQ-Datei-Änderung in diesem ADR.
4. **Python-POC-Plugin-Zukunft** (`integrations/hermes-agent-plugin`): Build-Generierung
   vs. eigenständige SemVer — Festlegung durch die zuständige Rolle.
5. **`engines.hermes`-Durchsetzung:** nur bei tatsächlicher Validierung Vertrag, sonst
   entfernen (`-101`).

---

*Erstellt durch `senior-developer` am 2026-10-03. Status `proposed` — begründete
Empfehlung; die Freigabe erfolgt durch User/Review, nicht durch den Autor.
Kein Produktcode, keine Migration, kein Push.*
