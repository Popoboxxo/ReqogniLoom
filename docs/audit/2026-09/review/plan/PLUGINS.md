---
type: PLAN
scope: audit-review-2026-09-plugins
status: final
date: 2026-10-01
author_agent: planner
epic: PLUG — Native Plugins
branch: chore/audit-review-2026-09
parent: IMPLEMENTATION_PLAN.md
---

# Epic PLUG — Native Plugins (Hermes / Claude-Code POC)

> Host-Integration bleibt BLOCKED; planbar ist die HTTP-/Code-Ebene. `101` ist auf **Low**
> herabgestuft (Manifest-Typ verwechselt) — kein High-Fix. **Aufwand:** verbindliche
> PT-Spannen in `plan/EFFORT_ESTIMATES.md` §1; die `Aufwand: S/M/L`-Angaben hier sind nur
> Groborientierung.

## PLUG-01 — Hermes-`TypeError` + Fixture-Falschgrün (P0, W1)

- **Findings:** 115, 114
- **Ort:** `integrations/hermes-agent-plugin/__init__.py:75-83` (`', '.join(missing)` über
  Dicts), Aufrufer `:110,120,127`, Fang nur `:162` (`except ReqogniLoomError`);
  Server liefert Dicts `application/interview_service.py:392,428`; Fixture
  `tests/test_slash_command.py:40` (String-Liste) verdeckt es
- **Zielverhalten:** `_fmt_state` verarbeitet Dict-förmige `missing_fields`; die verletzte
  „Never raises"-Zusage wird eingehalten oder der Docstring korrigiert. Fixture wird auf den
  echten Serververtrag (Dicts) umgestellt.
- **Akzeptanz:** `start`/`status`/`answer` mit nicht-leeren `missing_fields` werfen keinen
  `TypeError`; ein Regressionstest mit Dict-Fixture ist rot vor dem Fix.
- **Test:** pytest (Plugin-Suite) — Fixture-Korrektur macht den Critical reproduzierbar.
- **Aufwand:** S · **Risiko/Rollback:** gering (POC-Plugin) · **Deps:** — · **ADR:** —

## PLUG-02 — Plugin-Pagination `next` (P1, W2)

- **Findings:** 109
- **Ort:** `hermes-plugin/reqogniloom/src/api.ts:149-152` (nur `results`),
  `reqogniloom_client.py:136-139`; Server `serializers.py:360` (PAGE_SIZE 25), 401 Workspaces
- **Zielverhalten:** Beide Clients folgen `next`/`count`, bis die gewünschte Seite erreicht ist.
- **Akzeptanz:** Ziel-Workspace auf `-modified_at`-Rang 400 ist über das Plugin erreichbar.
- **Test:** pytest (Client) + Frontend/Vitest-Unit-Test; Live gegen 401-Workspace-Stack.
- **Aufwand:** S · **Risiko/Rollback:** gering · **Deps:** INT-05 (Pagination-Kontrakt) · **ADR:** —

## PLUG-03 — Plugin-Vertrag (P1, W2)

- **Findings:** 111, 112, 113, 117, 110
- **Ort:** `__init__.py:138` (`artifact_id` existiert nicht), `:62` (Help lowercase);
  `interview_views.py:207-209` (kein `count`); `state.ts:196-198` + `ConnectedView.tsx:6-24`
  (ErrorBanner fehlt in `connected`); `SKILL.md:20-42` (10 interview-Tools ungewhitelistet)
- **Zielverhalten:** `formalize` liest `resulting_artifact_ids`; `/interviews/` liefert `count`;
  Fehler ist im `connected`-Zustand sichtbar; interview-Tools sind gewhitelistet oder die
  Skill-Doku korrigiert; Hilfetext/Buttons konsistent PascalCase.
- **Akzeptanz:** `open interviews` zeigt echten Zähler; formalize gibt IDs aus; ein
  fehlgeschlagenes `openInterviews` zeigt einen Fehler.
- **Test:** pytest + Vitest; Live-HTTP. · **Aufwand:** M · **Risiko/Rollback:** gering ·
  **Deps:** PLUG-01, INT-05 · **ADR:** —

## PLUG-04 — Plugin-/Server-Versions-SSOT + Install-Doku (P2, W3)

- **Findings:** 106, 107, 108, 100, 101, 102–105
- **Ort:** `plugin.yaml:2`/`dashboard/manifest.json:6` (`0.1.0`); `mcp_server/protocol_handler.py:503-505`
  + `views.py:431` (`1.0.0` hart); `version.py:89-103` (`unknown`); `.gitignore:2` (`dist/`);
  `hermes-plugin.json:7,14-20,36,40-46` (Command nie registriert, Felder dekorativ)
- **Zielverhalten:** **ADR (vii) entscheidet** Versions-SSOT; danach Server-/Plugin-Version
  konsistent, `/api/v1/version/` belegt, `contributes.commands` registriert oder entfernt,
  Hermes-Installationsdoku ergänzt.
- **Akzeptanz:** `serverInfo.version` == `VERSION` (oder dokumentierte Plugin-SemVer);
  `/version/` liefert reale Werte; Command-Handler existiert.
- **Test:** pytest (Version-Parität) + Build-Test. · **Aufwand:** M · **Risiko/Rollback:**
  Client-Kompatibilität → ADR-gesteuert. · **Deps:** ADR vii · **ADR:** vii

### Versionierungs-Traceability — entschieden (2026-10-13, Issue #1138 / Finding 002-02)

**Entscheidung: Option B — Plugin-Versionierung ist Nicht-Produkt-Zusage, kein REQ.**

Begründung:

- ADR-017 (`docs/se/ADR/ADR-017_plugin_server_versions_ssot.md`, Status `accepted`,
  2026-10-03) trägt die Entscheidung bereits im Titel: *„`VERSION` ist SSOT der
  Server-Version; Plugin-Versionierung ist Nicht-Produkt-Zusage (Dritt-/POC-Plugins
  führen eigene SemVer mit `minServerVersion`)"*. Ein REQ hätte genau diesen Satz
  konterkariert — die Anforderung wäre das Gegenteil dessen, was das akzeptierte ADR
  festschreibt.
- Der Server-Teil ist durch `affected_reqs` von ADR-017 ohnehin abgedeckt
  (`REQ-L1-005`, `REQ-L1-006`, `REQ-L1-082`, `REQ-L2-MC-016`, `REQ-L2-MC-019`). Die
  Lücke war ausschließlich die **Plugin**-Seite, und die hat das ADR bewusst als
  Nicht-Produkt deklariert.
- Option A (REQ anlegen) hätte einen Widerspruch zwischen Anforderung und akzeptierter
  Architektur-Entscheidung erzeugt — genau die Inkonsistenz, die eine
  Traceability-Matrix *aufdecken* soll, nicht eine, die sie festschreiben soll.

Geltungsbereich dieses Statements: die **SemVer-Versionierung der ausgelieferten
Plugin-Bundles** (`dist/plugins/**`, TS-Hermes-Plugin) einschließlich des
`minServerVersion`-Kompatibilitätsfelds. Es ist **keine** Produktaussage: es gibt
keinen Kompatibilitätsvertrag an Dritte, keinen Support-Horizont und keine
Verpflichtung, dass ein Plugin-Version-Bump ein bestimmtes Server-Verhalten bedingt.

Nicht von diesem Statement erfasst (bleiben Anforderungen):

- `serverInfo.version` == `VERSION` — Server-SSOT, bereits REQ-abgedeckt.
- `/api/v1/version/` liefert reale Werte — Anforderung an den Server.

Verbleibender Teil von PLUG-04 (unberührt davon): `contributes.commands` registrieren
oder entfernen, Hermes-Installationsdoku ergänzen.

## PLUG-05 — Plugin-Timeout-/Fehlersemantik (P2, W3)

- **Findings:** 116 · **Ort:** `api.ts:113` (15 s), `state.ts:140`, `mcpClient.ts:60`
- **Zielverhalten:** Timeout und Connection-Fehler sind unterscheidbar.
- **Akzeptanz:** Timeout erzeugt eigene Meldung. · **Test:** Vitest. · **Aufwand:** S ·
  **Risiko/Rollback:** gering · **Deps:** — · **ADR:** —
