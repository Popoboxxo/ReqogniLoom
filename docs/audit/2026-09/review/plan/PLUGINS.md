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
> herabgestuft (Manifest-Typ verwechselt) — kein High-Fix.

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

## PLUG-05 — Plugin-Timeout-/Fehlersemantik (P2, W3)

- **Findings:** 116 · **Ort:** `api.ts:113` (15 s), `state.ts:140`, `mcpClient.ts:60`
- **Zielverhalten:** Timeout und Connection-Fehler sind unterscheidbar.
- **Akzeptanz:** Timeout erzeugt eigene Meldung. · **Test:** Vitest. · **Aufwand:** S ·
  **Risiko/Rollback:** gering · **Deps:** — · **ADR:** —
