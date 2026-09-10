# Pipeline `concept-driven-dev`

Execution mode: loop

1. invoke_subagent("explorer", "Codebase-/Kontext-Analyse (read-only): betroffene Dateien, Patterns, Risiko-Zonen, empfohlener Approach") → warten bis abgeschlossen
2. invoke_subagent("concept-specifier", "Technische Spezifikation schreiben (Interface-Contracts, Datenfluss, Akzeptanzkriterien) — XL-Tasks: vorab Systemdesign über concept-architect") → warten bis abgeschlossen

**review** — REPEAT_UNTIL Loop:
  - invoke_subagent("concept-specifier", "Spec/Design reviewen — Verdict APPROVED/CHANGES_REQUESTED/BLOCKED + Findings mit Severity")
  - invoke_subagent("concept-reviewer", "Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen

3. invoke_subagent("developer", "Implementierung gegen die freigegebene Spezifikation — Tier nach Task-Größe (S/M/L/XL): S junior-developer, M developer, L senior-developer, XL principal-developer") → warten bis abgeschlossen

**validate** — Parallel dispatch:
  - invoke_subagent("validator", "DoD-Check + Traceability")
  - invoke_subagent("tester", "Tests grün, keine Regression")

