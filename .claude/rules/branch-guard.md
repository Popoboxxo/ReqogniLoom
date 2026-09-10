# Branch-Guard

Verwende Feature-Branches (`feat/`, `fix/`, `chore/`). Keine Code-Änderungen direkt auf `main` oder `master`.

## Bekannte Grenzen

Die technische Durchsetzung (`orchestrator-guard.sh`) erkennt Git-Mutationen über eine Regex-/shlex-basierte Analyse des Bash-Befehls, kein vollständiger Shell-Parser. Bekannte Lücken: `eval "git commit ..."` wird nicht erkannt, direkte Schreibzugriffe auf `.git/` werden nicht geprüft, andere Git-Tools (`hub`, `gh repo ...`) sind nicht erfasst. Bewusster Trade-off, kein Bug (siehe Kommentar in `.claude/hooks/orchestrator-guard.sh:18-30`) — nur relevant für Nutzer, die sich vollständig auf den Schutz statt auf die Konvention verlassen.
