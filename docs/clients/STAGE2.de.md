# ReqogniLoom Stufe 2 — Store-Entwürfe (S1/S2)

> **Nur Entwürfe — keine Veröffentlichung.** Diese Artefakte werden erzeugt und
> im Repo geprüft, aber nichts wird publiziert. Die Workflows unten werden erst
> aktiv, nachdem die Entscheidungen E1–E7 beantwortet sind (Plan §8). Bis dahin
> sind sie Entwürfe.

## 1. Artefakt-Landkarte

| Artefakt | Stufe | Store | Erzeugt von | Veröffentlicht? |
|---|---|---|---|---|
| `.claude-plugin/marketplace.json` | S2 | Claude-Code-Marketplace (im Repo, E3) | `scripts/clients/render.py` | nein |
| `server.json` | S1 | Offizielle MCP-Registry | `scripts/clients/render.py` | nein |
| `.github/workflows/release-client-artifacts.yml` | — | GH-Release | geplant | nein |
| `.github/workflows/publish-npm.yml` | S5 | npm | geplant | nein |
| `.github/workflows/publish-marketplace.yml` | S2 | Claude-Marketplace | geplant | nein |
| `.github/workflows/publish-mcp-registry.yml` | S1 | MCP-Registry | geplant | nein |
| `.github/workflows/client-smoke.yml` | — | nächtlicher Smoke-Test | geplant | nein |

`claude plugin validate .` muss grün bleiben; `python scripts/clients/render.py --check`
ist das Drift-Gate. Details: [Plan §5](../plans/2026-10-04-one-click-client-installation.md),
[Client-Matrix](README.de.md).

## 2. Was noch fehlt

- npm-Paket/Scope (`@…/reqogniloom-opencode`, Installer) — E2.
- Codex-Marketplace-Anbindung (S4) — Format noch nicht verifiziert.
- Hermes-Katalogeintrag (S6) — Nous-Upstream-Prozess.
- Antigravity-Store (S7) — Preview-Plattform.
- Kimi-Upstream-Feature-Request (`kimi mcp add`) — E6.

## 3. Offene Entscheidungen E1–E7

| # | Entscheidung | Plan-Default (vorläufig) |
|---|---|---|
| E1 | MCP-Namespace | persönlich `io.github.popoboxxo` — vorläufig |
| E2 | npm-Scope | `@popoboxxo` — vorläufig |
| E3 | Marketplace-Repo | in diesem Repo — vorläufig |
| E4 | Betas in Stores | nein für kuratierte Stores; npm `next` |
| E5 | Antigravity in CI | self-hosted Runner oder manuell |
| E6 | Kimi-Stufe | L2 akzeptieren + Upstream-FR |
| E7 | Aggregatoren (S8) | später, nach W3 |

## 4. Entwurfs-Marker in server.json

Der vorläufige E1-Marker liegt in `server.json` → `_meta` →
`io.modelcontextprotocol.registry/publisher-provided` → `x-reqogniloom`
(`stage`: `2-draft`). Er muss vor der ersten Veröffentlichung bestätigt oder
entfernt werden.

```json
{
  "_meta": {
    "io.modelcontextprotocol.registry/publisher-provided": {
      "x-reqogniloom": { "stage": "2-draft" }
    }
  }
}
```

## 5. Checkliste vor der Veröffentlichung

- [ ] Den Platzhalter `https://<host>/mcp/` in `server.json` vor dem
  Veröffentlichen durch den echten Host ersetzen.
- [ ] Den vorläufigen E1-Namespace bestätigen oder ersetzen und den
  `2-draft`-`_meta`-Marker entfernen.
