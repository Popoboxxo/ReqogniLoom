# Pipeline `quick-fix`

Execution mode: sequential

1. invoke_subagent("developer", "Bugfix") → warten bis abgeschlossen
2. invoke_subagent("git", "Commit + Push") → warten bis abgeschlossen
