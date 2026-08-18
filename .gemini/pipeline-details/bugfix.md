# Pipeline `bugfix`

Execution mode: loop

1. invoke_subagent("bug-feature-analyzer", "Bug klassifizieren (Bug/User-Error/Feature/Out-of-Scope). Bei User-Error/Out-of-Scope → Pipeline stoppen.") → warten bis abgeschlossen
2. invoke_subagent("developer", "Bugfix implementieren") → warten bis abgeschlossen

**review** — REPEAT_UNTIL Loop:
  - invoke_subagent("developer", "Code-Qualität, Blast-Radius, SOLID/DRY prüfen")
  - invoke_subagent("code-reviewer", "Review / Critic feedback")
  Max iterations: 2 → Erfolg pruefen; bei Abbruch User benachrichtigen

3. invoke_subagent("documenter", "CODEBASE_OVERVIEW und Session-Erkenntnisse aktualisieren") → warten bis abgeschlossen
