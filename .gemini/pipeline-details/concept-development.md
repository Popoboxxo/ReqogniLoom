# Pipeline `concept-development`

Execution mode: loop

1. invoke_subagent("ideation", "Recherche: Stand der Technik, Optionen, Quellen, Trade-offs") → warten bis abgeschlossen

**concept** — REPEAT_UNTIL Loop:
  - invoke_subagent("ideation", "Konzept/Design-Doc erstellen und Review-Feedback einarbeiten")
  - invoke_subagent("concept-reviewer", "Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen

2. invoke_subagent("requirements", "Konzept in REQs überführen") → warten bis abgeschlossen
