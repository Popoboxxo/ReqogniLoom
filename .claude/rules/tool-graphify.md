# External Tool: graphify

> graphify — lokal installiertes CLI-Tool. Baut das Repo als Wissensgraph auf (Community Detection, God Nodes, Query/Path/Explain). Wird NICHT von agent-meta bereitgestellt, muss lokal installiert sein.

---

## graphify
`graphify` ist ein lokal installiertes CLI-Tool für Architektur-/Datei-
Beziehungsfragen. Bei Bedarf `graphify-out/` prüfen bzw. `/graphify`
nutzen. Nicht auf dieser Maschine installiert? Die Hook-Wrapper unten
laufen dann folgenlos durch (exit 0), nichts wird blockiert.

## Hook-Wrapper

- `hooks/0-external/graphify-search-guard.sh`
- `hooks/0-external/graphify-read-guard.sh`

## Erlaubte Injektionen

- `.claude/skills/graphify` (skill) — Claude-Code-Skill (SKILL.md + references), vom graphify-Installer selbst verwaltet

---

*Generiert von agent-meta aus `config/external-tools-registry.yaml` — nicht manuell bearbeiten.*
