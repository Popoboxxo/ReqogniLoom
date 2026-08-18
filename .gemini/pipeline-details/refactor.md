# Pipeline `refactor`

Execution mode: loop

1. invoke_subagent("senior-developer", "Blast-Radius-Analyse: Scope bestimmen, betroffene Dateien identifizieren, Risiken bewerten") → warten bis abgeschlossen
2. invoke_subagent("developer", "Refactoring implementieren ohne funktionale Änderungen") → warten bis abgeschlossen

**review** — REPEAT_UNTIL Loop:
  - invoke_subagent("developer", "Refactoring auf Clean Code, SOLID, DRY prüfen und Feedback einarbeiten")
  - invoke_subagent("code-reviewer", "Review / Critic feedback")
  Max iterations: 2 → Erfolg pruefen; bei Abbruch User benachrichtigen

3. invoke_subagent("git", "Commit + Push") → warten bis abgeschlossen
