# Bugfix-Hub — Externe Anbindungen, Plugins, API & Integrationen

| Feld | Wert |
|---|---|
| **Status** | Aktiv (laufender Index) |
| **Angelegt** | 2026-10-05 |
| **Basis** | `v1.8.0-beta.18`, GitHub-Issue-Bestand 2026-10-05 |
| **Arbeitsplan** | [`docs/plans/2026-10-05-bugfix-hub-integrationen.md`](../plans/2026-10-05-bugfix-hub-integrationen.md) |
| **Leit-Plan** | [`docs/plans/2026-10-04-one-click-client-installation.md`](../plans/2026-10-04-one-click-client-installation.md) · Issue #1171 |
| **Scope** | Fremd-Clients/-Provider, MCP-Server-Surface, REST-/OpenAPI-Contract, Plugin-Runtime, Supply-Chain |

## 1. Zweck

Dieser Hub bündelt die **offenen GitHub-Issues**, die Fremdsysteme betreffen, zu wenigen
lauffähigen **Fix-Bundles**. Er ist der Einstiegspunkt (Index + Status-Board); die operative
Reihenfolge, Arbeitspakete und Definition-of-Done liegen im Arbeitsplan (s. o.).

Ziel ist nicht „alle Issues auf einmal", sondern: pro Bundle ein **belegter** Fix-Pfad
(Reproduktion → Fix → Verifikation gegen den echten Client/Provider → Issue-Closure).

## 2. Scope-Abgrenzung

**In Scope (extern):**
- **Client-Onboarding & Fremd-Harness:** Claude Code, Codex, OpenCode, Kimi Code, Antigravity, Hermes.
- **MCP-Server-Surface:** Paritätslücken MCP ↔ REST, Tool-Suche, Tool-Schemas.
- **REST-API & OpenAPI:** Envelope-, Routing-, Schema- und Fehler-Contract.
- **Externe LLM-Provider:** Timeouts, Fehler-Mapping, Response-Parsing, Honcho-Dialektik.
- **Plugins:** Hermes Desktop/Agent, Bluepencil-Review-Layer, Plugin-Versionierung.
- **Supply-Chain & Token-Scope:** Store-Publikation, npm-Plugin, workspace-scoped API-Tokens.

**Out of Scope (eigene Hubs/Backlog):**
- Reine UI-/Layout-Bugs ohne Integrationsbezug (#1176, #1094, #1095, #1089, #801 …).
- Datenmodell-Kampagnen (#1178 Duplikaterkennung, #941/#934 Attribut v3).
- RLS-/Security-Härtungskampagnen (#1179–#1184, #1166 DB-Pool als Betriebsthema — nur beobachtend verlinkt).
- SE-Kaskade/Traceability-Grundsatzentscheidungen (#877, #878, #879, #1110).

> Grenzfälle: #1166 (DB-Pool) und #1165 (LLM-Timeout) sind Betriebs-/Provider-Themen und daher
> über Bundle **B2** bzw. als Abhängigkeit gelistet, nicht als eigener Code-Fix hier.

## 3. Prozess (Triage → Fix → Closure)

```
Issue (open)
  │ 1. Triage: Bundle + Prio zuordnen, Reproduktion prüfen
  ▼
Bundles (dieser Hub)  ──►  Arbeitsplan (APs, DoD, Aufwand)
  │ 2. Fix auf feat/fix-Branch, Test/Beleg
  ▼
Verifikation gegen echten Fremd-Client/Provider (Smoke-Test-Nachweis)
  │ 3. PR + Issue-Closure (Closes #NNN)
  ▼
Status-Board aktualisiert
```

`fix(bundle-x): … (Closes #NNN)` — jede Schließung wird im Status-Board nachgeführt.

## 4. Status-Board

Legende Prio: **P1** = blockiert produktiven Fremd-Einsatz · **P2** = Funktion eingeschränkt · **P3** = Komfort/Doku.
Status: `open` → `triaged` → `in-progress` → `verify` → `closed`.

| Issue | Titel (kurz) | Bundle | Prio | Status |
|---|---|---|---|---|
| #1171 | Client-Doku One-Click je Harness (DE/EN) | B0 | P1 | triaged |
| #1169 | Codex headless: Approval-Bypass + `wire_api=responses` | B0 | P1 | verify |
| #649 | Importierbarer Hermes-Skill (Connector) | B0 | P2 | triaged |
| #92 | Workspace-spezifische API-Tokens + MCP-Config-Copy | B0 | P2 | triaged |
| #1138 | Traceability-Anker für Plugin-Versionierung | B0 | P2 | triaged |
| #1164 | Interview MCP↔REST-Asymmetrie (`set_target`/`chat`) | B1 | P1 | verify |
| #1098 | Kein workspace-weites TraceLink-Enumerieren über MCP | B1 | P2 | verify |
| #1097 | `main_goal` nicht per Workspace über MCP auflistbar | B1 | P2 | verify |
| #1170 | `artifact_search` ohne Relevanzschwelle | B1 | P3 | verify |
| #1101 | VCRM MCP-only, im OpenAPI nicht sichtbar | B1 | P3 | verify |
| #1133 | MCP-Live-Stack-Rollentests nicht self-seeding | B1 | P3 | verify |
| #1153 | Honcho-Dialektik HTTP 500 (`MissingSessionID`) | B2 | P1 | triaged |
| #1186 | Preflight-Smoke: `x-opencode-session` erreicht Provider | B2 | P2 | verify |
| #1163 | `check_consistency` TypeError bei `score: null` | B2 | P1 | verify |
| #1165 | `architecture.decompose` LLM-Timeout → generischer 500 | B2 | P1 | verify |
| #1152 | Hermes-Plugin `Cancel` ruft `interview.abandon` nicht | B3 | P2 | verify |
| #988 | Bluepencil-Bundle ohne Identity-Fix („anonymous") | B3 | P2 | triaged |
| #1177 | REST-Inkonsistenzen (Envelope/404/Bindestrich/openapi.json) | B4 | P1 | verify |
| #1185 | Import-Fehlerantwort leakt DB-Interna (CWE-209) | B4 | P1 | verify |
| #1155/#1156 | Honcho-Langzeitgedächtnis + „Zuhören & Antizipieren" | B2/B0 | P2 | triaged |

## 5. Bundles (Kurzfassung)

| Bundle | Name | Issues | Ziel |
|---|---|---|---|
| **B0** | Client-Onboarding / One-Click | #1171, #1169, #649, #92, #1138 | Jeder Harness in **einem** Befehl angebunden, Doku DE/EN, Store-Stufe |
| **B1** | MCP-Surface-Parität | #1164, #1098, #1097, #1170, #1101, #1133 | Keine MCP↔REST-Lücke; Surface dokumentiert & getestet |
| **B2** | Externe LLM-/Provider-Robustheit | #1153, #1186, #1163, #1165 | Provider-Fehler deterministisch, korrekt gemappt, belegt |
| **B3** | Plugin-Runtime & Fremd-Bundles | #1152, #988 | Plugins bedienen den echten Serververtrag |
| **B4** | API-Contract-Konsistenz | #1177, #1185 | Einheitlicher Envelope, saubere Fehler, standardkonformes OpenAPI |

Details, Arbeitspakete, Aufwände und DoD: siehe Arbeitsplan §3.

> **B0 Stufe 1 in place:** Registry (`clients/registry.yaml`), Renderer
> (`scripts/clients/render.py`), Doku DE/EN (`docs/clients/**`), Skripte
> (`scripts/clients/install.sh` / `verify.sh`) und CI-Gate
> (`.github/workflows/client-artifacts-check.yml`) sind umgesetzt; Renderer `--check` grün (16 Artefakte: 14 Client + 2 Store).
>
> **B0 Stufe 2 — Drafts liegen:** `.claude-plugin/marketplace.json`, `server.json` (beide aus `VERSION`) und fünf Workflow-Drafts (`release-client-artifacts`, `publish-npm`, `publish-marketplace`, `publish-mcp-registry`, `client-smoke`) plus `docs/clients/STAGE2.md` sind vorbereitet; **keine Publikation aktiv** (Trigger nur `workflow_dispatch`, Entscheidungen E1–E7 offen).

## 6. Verwandte Dokumente

- Leit-Plan One-Click: `docs/plans/2026-10-04-one-click-client-installation.md`
- MCP-Surface: `docs/api/MCP-SURFACE.md` · REST: `docs/api/REST-CONVENTIONS.md`
- Client-Installation (generiert aus `clients/registry.yaml`): `docs/clients/`
- Agent-Templates: `docs/agent-templates/INSTALL.md`, `docs/agent-templates/DOMAIN_MODEL.md`

## 7. Kennzahlen

| Metrik | Ziel |
|---|---|
| Issues in B0–B4 auf `closed`/`verify` | 100 % mit Beleg |
| MCP↔REST-Paritätsgaps (B1) | 0 |
| Client-Harnesse auf L2 / L3 | 6/6 (L2) · ≥4/6 (L3) |
| Doku-Widersprüche zwischen Client-Dateien | 0 (CI-erzwungen, B0) |
| „Client verbindet nicht"-Supportfälle | sinkend |
