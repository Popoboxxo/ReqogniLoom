# ReqogniLoom Stufe 2 — Store-Entwürfe (S1/S2)

> **Nur Entwürfe — keine Veröffentlichung.** Die Artefakte unten werden erzeugt
> und im Repo geprüft, aber nichts wird publiziert. Die Publikations-Workflows
> sind Entwürfe und laufen nur über `workflow_dispatch`; sie werden erst in den
> W-Wellen aktiv (Plan §5.4).
>
> **Die Entscheidungen E1–E4 und E6 sind ENTSCHIEDEN (2026-10-09); E5 und E7
> sind vertagt** (siehe §3). Die Veröffentlichung bleibt inaktiv.

## 1. Artefakt-Landkarte

| Artefakt | Stufe | Store | Erzeugt von | Veröffentlicht? |
|---|---|---|---|---|
| `.claude-plugin/marketplace.json` | S2 | Claude-Code-Marketplace (im Repo, E3) | `scripts/clients/render.py` | nein |
| `server.json` | S1 | Offizielle MCP-Registry | `scripts/clients/render.py` | nein |
| `.github/workflows/release-client-artifacts.yml` | — | GH-Release | Entwurfs-Workflow (nur `workflow_dispatch`) | nein |
| `.github/workflows/publish-npm.yml` | S5 | npm | Entwurfs-Workflow (inert, `workflow_dispatch`) | nein |
| `.github/workflows/publish-marketplace.yml` | S2 | Claude-Marketplace | Entwurfs-Workflow (inert, `workflow_dispatch`) | nein |
| `.github/workflows/publish-mcp-registry.yml` | S1 | MCP-Registry | Entwurfs-Workflow (inert, `workflow_dispatch`) | nein |
| `.github/workflows/client-smoke.yml` | — | nächtlicher Smoke-Test | Entwurfs-Workflow (`workflow_dispatch`) | nein |

`claude plugin validate .` muss grün bleiben; `python scripts/clients/render.py --check`
ist das Drift-Gate. Details: [Plan §5](../plans/2026-10-04-one-click-client-installation.md),
[Client-Matrix](README.de.md).

## 2. Was noch fehlt

- npm-Paket(e) — Scope **entschieden** (`@popoboxxo`, E2), Paket noch nicht veröffentlicht (W2).
- Codex-Marketplace-Anbindung (S4) — Format noch nicht verifiziert (W4).
- Hermes-Katalogeintrag (S6) — Nous-Upstream-Prozess (W5).
- Antigravity-Store (S7) — Preview-Plattform (W4).
- Kimi-Upstream-Feature-Request (`kimi mcp add`) — **L2 akzeptiert** (E6), FR noch zu stellen.
- Konto-Voraussetzungen für die Veröffentlichung (E1-Namespace, E2-Scope) — siehe §4.

## 3. Entscheidungen E1–E7

| # | Entscheidung | Ergebnis (2026-10-09) |
|---|---|---|
| E1 | MCP-Namespace | **ENTSCHIEDEN** — persönlich `io.github.popoboxxo` |
| E2 | npm-Scope | **ENTSCHIEDEN** — `@popoboxxo` |
| E3 | Marketplace-Repo | **ENTSCHIEDEN** — in diesem Repo (`.claude-plugin/marketplace.json`) |
| E4 | Betas in Stores | **ENTSCHIEDEN** — nein für kuratierte Stores (S3/S6); Pre-Releases über npm `next` |
| E5 | Antigravity in CI | **VERTAGT** — vor W4 entscheiden |
| E6 | Kimi-Stufe | **ENTSCHIEDEN** — L2 akzeptieren + Upstream-Feature-Request stellen |
| E7 | Aggregatoren (S8) | **VERTAGT** — nach W3 |

## 4. Checkliste vor der Veröffentlichung

- [ ] Den Platzhalter `https://<host>/mcp/` in `server.json` vor dem
  Veröffentlichen durch den echten Host ersetzen.
- [ ] Das npm-Org-/Scope-Konto `@popoboxxo` anlegen/beanspruchen (E2).
- [ ] Den MCP-Registry-Namespace `io.github.popoboxxo` anlegen/beanspruchen (E1).
