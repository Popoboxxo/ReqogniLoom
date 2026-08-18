# Pipeline `docs-update`

Execution mode: sequential

1. invoke_subagent("documenter", "Dokumentation aktualisieren") → warten bis abgeschlossen
2. invoke_subagent("git", "Commit + Push") → warten bis abgeschlossen
