# ProjectAtlas Setup — Erkenntnisse

**Datum:** 2026-08-18
**Repo:** ReqogniLoom
**Quelle:** https://github.com/styler-ai/ProjectAtlas

## Was ist ProjectAtlas

Rust-natives CLI + MCP-Server. Baut lokale SQLite-Index (`.projectatlas/projectatlas.db`)
über Ordner, Dateien, Symbole, Code-Beziehungen. Agenten navigieren gezielt statt
ganze Dateien zu lesen. Laut Hersteller >90% Token-Ersparnis bei Codebase-Recherche.

## Ausgangslage

Binary war bereits installiert (`/home/dduchrow/.local/bin/projectatlas`, v0.4.4)
und `projectatlas init` bereits gelaufen — `.projectatlas/` mit Index (280 MB DB)
existierte schon, aber **kein Host war verkabelt**: weder Claude Code noch
opencode noch Antigravity hatten den MCP-Server registriert.

## Was gemacht wurde

1. **Claude Code** — Eintrag `projectatlas` in `.claude/settings.json` unter
   `mcpServers` ergänzt (neben bestehendem `a2a-handoff`).
2. **opencode** — Eintrag `projectatlas` in `opencode.json` (Repo-Root) unter
   `mcp` ergänzt (neben bestehendem `a2a-handoff`).
3. **Antigravity** — Google-IDE, kein natives ProjectAtlas-Template vorhanden
   (`projectatlas mcp-config --harness` kennt nur `mcp-json`, `codex`,
   `claude-code`, `opencode`). Config manuell nach Antigravity-Konvention
   erzeugt unter `.agents/mcp_config.json` (Workspace-lokaler Pfad, analog zu
   `.cursor/mcp.json` bzw. `.windsurf/mcp_config.json`). Antigravity kennt
   zusätzlich einen globalen Pfad `~/.gemini/config/mcp_config.json` — hier
   bewusst nicht angefasst, da global und nicht projektspezifisch.
4. **`.gitignore`** — `.projectatlas/` (280 MB Index-DB, reine Laufzeitdaten)
   und `.agents/mcp_config.json` (enthält absolute lokale Pfade, maschinenspezifisch)
   ergänzt. Beides gehört nicht ins Repo.
5. Index war 5 Pfade veraltet (durch die neu angelegten Config-Dateien selbst)
   → `projectatlas watch --once` gefahren, danach `health-check` und `overview`
   sauber gelaufen (2486 Dateien, 446 Ordner indiziert).

## Wichtige Erkenntnis für Folge-Sessions

- Alle drei Host-Configs zeigen auf **denselben** MCP-Server-Prozess
  (`projectatlas ... mcp`), nur das Umschließungs-JSON unterscheidet sich je
  Host-Schema.
- Pfade in den generierten Configs sind **absolut und maschinenspezifisch**
  (`/home/dduchrow/.local/bin/projectatlas`, `/home/dduchrow/Repos/ReqogniLoom/...`).
  Bei Rechnerwechsel oder anderem User müssen alle drei Dateien neu generiert
  werden — dafür reicht `projectatlas mcp-config --harness <ziel>`.
- Die DB ist projektlokal und wird nicht versioniert — jeder Checkout braucht
  einmalig `projectatlas init` bzw. `watch --once`.
- Nach jeder strukturellen Änderung am Repo (neue Top-Level-Dateien/Ordner)
  meldet `health-check` ggf. `refresh_required` — dann hilft `projectatlas
  watch --once`.

## Nicht gemacht (bewusst)

- Kein `codex`-Harness-Config erzeugt — nicht angefragt.
- Globale Antigravity-Config (`~/.gemini/config/mcp_config.json`) nicht
  angefasst — außerhalb des Projekt-Scopes, würde alle Repos betreffen.
