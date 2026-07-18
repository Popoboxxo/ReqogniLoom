# `systemagents/` — Project-Owned Agent Artifacts

Permanenter, versionierter Ort für Agenten-Definitionen und verwandte Artefakte,
die **zu ReqFlow selbst gehören** — nicht zum `agent-meta`-Framework (Submodule
`.agent-meta/`) und nicht zu dessen generiertem Output (`.claude/`, `.gemini/`,
`.opencode/`, `.continue/` — alle vollständig gitignored, siehe `.gitignore`
Zeile 3 `.claude` sowie den `agent-meta managed`-Block).

Dieses Verzeichnis ist **git-getrackt**. Alles hier überlebt Merges, Branches,
Reverts wie normaler Code — im Gegensatz zu `.claude/3-project/`, das nie
committet wird.

## Warum nicht `.claude/3-project/`?

`.claude/3-project/<role>.md` wird von `sync.py` **nicht** als vollständige
Agenten-Quelle gescannt (`scripts/lib/agents.py::collect_sources()` liest nur
`3-project/` **innerhalb des `.agent-meta`-Submodules**, nicht im Projekt-Root).
Ein Entwurf dort ist reiner Text ohne jede Wirkung — Claude Code lädt Subagenten
ausschließlich aus `.claude/agents/*.md`. Der alte Entwurf `reqflow.md` lag genau
dort und wurde hierher verschoben (`git log` / PR-Historie zeigt die Migration).

`.claude/3-project/<role>-ext.md` (mit `-ext`-Suffix) ist etwas anderes: additive
Erweiterung eines **bereits existierenden, von agent-meta generierten** Agenten
(z.B. `rf-reqflow-ext.md` für einen registrierten `reqflow`-Agenten). Das ist
kein Ersatz für einen eigenständigen, noch nicht registrierten Agenten wie diesen.

## Struktur

```
systemagents/
  README.md          # diese Datei
  reqflow.md          # Quelle für den ReqFlow-Operator-Agenten
  (weitere projekt-eigene Agenten künftig hier)
```

## Zusammenhang mit `.claude/agents/`

Claude Code lädt Subagenten **ausschließlich** aus `.claude/agents/*.md`. Dieses
Verzeichnis ist vollständig gitignored und wird von `sync.py` generiert/verwaltet.

`reqflow` ist **kein** von `agent-meta` verwalteter Agent — er taucht weder in
`.meta-config/project.yaml` (`roles:`-Liste) noch in
`.agent-meta/config/role-defaults.yaml` auf. Damit die Rolle tatsächlich wirkt,
liegt aktuell eine **manuelle 1:1-Kopie** unter `.claude/agents/reqflow.md`.

**Aktueller Stand (Stand: Migration auf `feat/reqflow-self-migration`):**
- Quelle (versioniert): `systemagents/reqflow.md`
- Wirksame Kopie (gitignored, von Claude Code geladen): `.claude/agents/reqflow.md`
- Beide Dateien sind aktuell inhaltsgleich.

### Nach jeder Änderung an `systemagents/reqflow.md`

```bash
cp systemagents/reqflow.md .claude/agents/reqflow.md
```

(Windows ohne Git-Bash: `copy systemagents\reqflow.md .claude\agents\reqflow.md`)

Es gibt **noch keinen automatischen Build-/Sync-Schritt**, der das für dich tut.
Das ist der offene Punkt dieser Migration (siehe unten).

## Ist die Kopie in `.claude/agents/` sync-sicher?

Ja — geprüft in `scripts/lib/agents.py::sync_agents_for_provider()`. Dort schützt
der Manifest-Mechanismus `.claude/agents/.agent-meta-managed`:

- `sync.py` löscht in `.claude/agents/` nur Dateien, deren Name **bereits einmal
  im Manifest stand** (`previously_managed`). Eine Datei, die nie Teil eines
  generierten Rollen-Sets war — wie `reqflow.md`, solange die Rolle nicht in
  `.meta-config/project.yaml` registriert wird — wird von `sync.py` **nie**
  angefasst oder gelöscht, auch nicht bei künftigen `update-meta`/`upgrade-meta`-Läufen.
- Das gilt nur für den tatsächlich aktiven Codepfad `sync_agents_for_provider()`
  (verifiziert: `sync.py` ruft ausschließlich diese Funktion auf, nie die ältere
  `sync_agents()` ohne Manifest-Schutz — die ist toter Code).

Fazit: Die manuelle Kopie ist dauerhaft stabil, aber **nicht automatisch
aktuell** — sie divergiert stillschweigend, wenn du die Quelle änderst und den
Kopierschritt vergisst.

## Offener Punkt / TODO

Kein automatischer Kopier-/Build-Schritt vorhanden. Optionen für später (nicht
Teil dieser Migration, erfordert Rücksprache mit `agent-meta-manager`):

1. **Generisches Framework-Feature vorschlagen** (`meta-feedback`, Label
   `new-agent` oder `new-platform-agent`): ein offizieller Mechanismus für
   projekt-eigene, nicht-generische Rollen, die `sync.py` aus einem
   projekt-lokalen Verzeichnis (z.B. `systemagents/`) automatisch nach
   `.claude/agents/` kopiert und im Manifest führt.
2. **Kleines projekt-eigenes Hilfsskript** (z.B. `scripts/sync-project-agents.sh`),
   das `systemagents/*.md` nach `.claude/agents/*.md` spiegelt — bewusst
   *nicht* Teil von `agent-meta`, sondern ein reines ReqFlow-Tooling-Skript.

Bis eine der beiden Optionen umgesetzt ist: manueller `cp` nach jeder Änderung.
