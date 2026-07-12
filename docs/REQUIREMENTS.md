<!-- All requirements have been successfully migrated to the SE Cascade in docs/se/L1/Gesamtsystem/L2/... -->

## Frontend Requirements — Cluster A (2026-07-12)

| REQ-ID | Kategorie | Titel | Beschreibung | Status |
|--------|-----------|-------|-------------|--------|
| REQ-001 | Functional | Versioning/Diff-Service | Versionsliste und Diff-Ansicht müssen in allen Views zuverlässig funktionieren. Kein "error [object Object]" in der UI; Diff darf nicht dupliziert angezeigt werden. | Active |
| REQ-002 | Functional | Trace-Link-Resolver | Alle Trace-Links müssen den lesbaren Titel/Namen des referenzierten Elements anzeigen, nicht nur die ID. Gilt für Anforderungen, Architektur, ADRs und Impact-Analyse. | Active |
| REQ-003 | Functional | Einheitliches Tree-Modul | Ein gemeinsames WorkspaceTree-Komponente wird in allen Ansichten (Bedarfe, Anforderungen, Architektur, ADRs, Risiken, Probleme, Testfälle, Diagramme) verwendet. Einheitliches Aussehen und Verhalten: kompakte Tree-Rows, Expand/Collapse, optionale Level-Badges (L0-L4) für Architektur, Status-Badges für alle anderen Views. Kein Karten-Layout mehr in der linken Navigationsleiste. | Active |
| REQ-004 | Functional | i18n-Leak beheben | Rohe Translation-Keys dürfen nicht in der UI angezeigt werden. Bestätigte Fälle: editor.status (ADRs, Risiken, Testfälle), workspace.create.submit (Neuer-Workspace-Button). Alle vergleichbaren Fälle beheben. | Active |
| REQ-005 | Functional | Link-Erstellen-Dialog vereinheitlichen | Ein gemeinsamer CreateTraceLinkDialog wird in Architektur, Impact-Analyse (TraceabilityView) und ADRs verwendet. Enthält Suchfeld, Elementtyp-Filter und zeigt Titel (nicht nur IDs). Öffnet als Modal (kein Layout-Shift). | Active |
| REQ-006 | Functional | Soft-Delete-Statusmodell | Architektur-Elemente, ADRs und Glossar-Einträge können nicht mehr von normalen Nutzern physisch gelöscht werden. Stattdessen: Status outdated/deprecated/deleted (lifecycle_status bei ArchitectureElement/GlossaryTerm; Adr.Status.DELETED). Gelöschte Elemente werden in Normalansicht ausgeblendet (?include_deleted=true für Admin-Zugriff). Hartes Löschen nur via Django Admin. TODO: Requirements/StakeholderNeeds haben unvalidiertes status-Feld — Soft-Delete dort in separatem Ticket nachziehen. | Active |
