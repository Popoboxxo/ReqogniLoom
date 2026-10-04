# WP-3b Evidence 01 - i18n-Vollinventar

Scope: frontend/src (370 Prod-Dateien, 256 Test-Dateien, 626 TS/TSX gesamt).
Scanner: Block-Kommentare und //-Zeilen entfernt, Test-Dateien getrennt gezaehlt,
Vorzeichenpruefung gegen params.set( / document.createElement( / .split( / await import(.

Reproduktion: siehe wp3b-00-methodik.md.

## 1. Kopfzahlen

```
LOCALE de=2120 en=2120 onlyde=0 onlyen=0
FILES total=626 prod=370 test=256
=== t() spellings RAW ===
  Trans                        2
  i18n.t( [t]                  9
  t(                           2402
=== t() spellings PROD ===
  Trans                        2
  t(                           2402
  TOTALprod=2404
distinct referenced all=1700 prod=1699
-- PROD-refs --
  missingBOTH=116 missingDEonly=0 missingENonly=0
-- ALL-refs --
  missingBOTH=116 missingDEonly=0 missingENonly=0
```

## 2. Fehlende Keys je Produktionsdatei (fehlen in BEIDEN Locales)

=== missingBOTH(prod) per file ===
components/BaselinesView/BaselinesPanels.tsx                     14
        baselines.added
        baselines.after
        baselines.before
        baselines.capturedItems
        baselines.changed
        baselines.compareA
        baselines.compareB
        baselines.compareNoChanges
        baselines.comparing
        baselines.field
        baselines.fieldChangesCount
        baselines.legacyEntry
        baselines.noCapturedItems
        baselines.removed
components/canvas/CanvasEditor.tsx                               14
        canvas.defaultLabel
        canvas.defaultText
        canvas.status.hint
        canvas.toolbar.connector
        canvas.toolbar.ellipse
        canvas.toolbar.fill
        canvas.toolbar.lineStyle
        canvas.toolbar.noFill
        canvas.toolbar.rect
        canvas.toolbar.snap
        canvas.toolbar.text
        canvas.toolbar.zoomFit
        canvas.toolbar.zoomIn
        canvas.toolbar.zoomOut
components/WorkspaceSettings/PermissionsSection.tsx              14
        permissions.artifact
        permissions.empty
        permissions.filterSelect
        permissions.grant
        permissions.hint
        permissions.level
        permissions.load
        permissions.noMembers
        permissions.selectUser
        permissions.title
        permissions.user
        permissions.userRequired
        permissions.workspaceWide
        permissions.workspaceWideShort
components/UserProfileSettings/ProfileSection.tsx                9
        profile.cancel
        profile.edit
        profile.firstName
        profile.lastName
        profile.nameHeading
        profile.noName
        profile.save
        profile.saved
        profile.saving
components/WorkspaceSettings/LlmSettingsSection.tsx              9
        save
        saving
        settings.llm.apiKey
        settings.llm.apiKeyNotSet
        settings.llm.baseUrl
        settings.llm.description
        settings.llm.modelName
        settings.llm.provider
        settings.llm.title
components/WorkspaceSettings/WorkspaceSettings.tsx               8
        settings.adminOnly
        settings.csvImport
        settings.decompositionLinkType
        settings.defaultLinkType
        settings.devModeHint
        settings.seModeHint
        settings.traceability
        settings.workspaceName
components/CsvImport/CsvImport.tsx                               7
        export.entityType
        export.errorGeneric
        export.reqifHint
        export.title
        import.moreErrors
        import.nothingWritten
        import.previewEmptyTitleRows
components/WorkspaceSettings/WorkflowPermissionsSection.tsx      7
        settings.noGlobalSourceHint
        settings.openInEditor
        settings.overrideMatrix
        settings.permissionConfig
        settings.permissionConfigHint
        settings.workflowConfig
        settings.workflowConfigHint
components/IcdView/SimilarIcdsPanel.tsx                          5
        icds.similar.empty
        icds.similar.findButton
        icds.similar.heading
        icds.similar.noEmbedding
        icds.similar.unavailable
components/BaselinesView/BaselinesView.tsx                       3
        baselines.compareSameBaseline
        baselines.compareSelectBoth
        baselines.summary
components/WorkspaceSettings/AiPromptsSection.tsx                3
        save
        saving
        settings.promptTemplates.interviewDescription
components/shared/TraceLinkPanel.tsx                             2
        actions.newLink
        actions.showAll
components/TestRuns/TestRunsList.tsx                             2
        editor.name
        testRuns.summary
components/NavigationShell/SidebarNavigation.tsx                 2
        nav.hideOptionalArtifacts
        nav.showOptionalArtifacts
components/UserProfileSettings/UserProfileSettings.tsx           2
        settings.visibility
        settings.visibilityFromPreset
components/UserProfileSettings/ApiKeysSection.tsx                1
        apiKeys.createNew
components/ArchitectureEditors/ArchitectureEditors.tsx           1
        arch.summary
components/AdminDialog/TriLabelOverviewDialog.tsx                1
        common.close
components/AdminDialog/SystemHealthDialog.tsx                    1
        common.close
components/DiagramView/DiagramView.tsx                           1
        diagrams.summary
components/GlossaryView/GlossaryView.tsx                         1
        glossary.summary
components/Goals/GoalsPage.tsx                                   1
        goals.summary
components/IcdView/IcdDetailPane.tsx                             1
        icds.similarInterfaces
components/IcdView/IcdView.tsx                                   1
        icds.summary
components/InterviewEditors/InterviewEditors.tsx                 1
        interviews.summary
components/NeedsEditors/NeedsEditors.tsx                         1
        needs.summary
components/PermissionMatrix/PermissionMatrixEditor.tsx           1
        permissionMatrix.capability.
components/WorkspaceSettings/PromptVariablesSection.tsx          1
        save
components/SystemSettings/SystemSettings.tsx                     1
        systemSettings.adminOnly
components/SystemSettings/EnforcementModePanel.tsx               1
        systemSettings.enforcementMode.meta
components/SystemSettings/PermissionDefaultsTab.tsx              1
        systemSettings.permissionDefaults.propagatedToast
components/shared/TraceSpine/TraceSpine.tsx                      1
        traceSpine.stationCount
components/WorkflowEditor/EntityTypeSelector.tsx                 1
        workflow.entitySelector.stateCount
components/WorkflowEditor/WorkflowEditorPage.tsx                 1
        workflow.toast.propagated
```

## 3. Fundstellen der fehlenden Keys (Datei:Zeile + Quelltext)

=== MISSING-BOTH locations ===
components/AdminDialog/SystemHealthDialog.tsx            L172   t(         {t("common.close", "Close")}
components/AdminDialog/TriLabelOverviewDialog.tsx        L61    t(         {t("common.close", "Close")}
components/ArchitectureEditors/ArchitectureEditors.tsx   L364   t(         t('arch.summary', { count: elements.length, defaultValue: `${elements.length}` }),
components/BaselinesView/BaselinesPanels.tsx             L57    t(         {t("baselines.capturedItems", "Captured items")}
components/BaselinesView/BaselinesPanels.tsx             L87    t(         {t("baselines.noCapturedItems", "No captured items.")}
components/BaselinesView/BaselinesPanels.tsx             L220   t(         <span>{t("baselines.compareA", "Baseline A (from)")}</span>
components/BaselinesView/BaselinesPanels.tsx             L237   t(         <span>{t("baselines.compareB", "Baseline B (to)")}</span>
components/BaselinesView/BaselinesPanels.tsx             L261   t(         ? t("baselines.comparing", "Comparing…")
components/BaselinesView/BaselinesPanels.tsx             L283   t(         label={t("baselines.added", "Added")}
components/BaselinesView/BaselinesPanels.tsx             L289   t(         label={t("baselines.removed", "Removed")}
components/BaselinesView/BaselinesPanels.tsx             L295   t(         label={t("baselines.changed", "Changed")}
components/BaselinesView/BaselinesPanels.tsx             L304   t(         {t("baselines.compareNoChanges", "No differences between the baselines.")}
components/BaselinesView/BaselinesPanels.tsx             L425   t(         {t("baselines.fieldChangesCount", {
components/BaselinesView/BaselinesPanels.tsx             L437   t(         <th className={styles.diffTh}>{t("baselines.field", "Field")}</th>
components/BaselinesView/BaselinesPanels.tsx             L438   t(         <th className={styles.diffTh}>{t("baselines.before", "Before")}</th>
components/BaselinesView/BaselinesPanels.tsx             L439   t(         <th className={styles.diffTh}>{t("baselines.after", "After")}</th>
components/BaselinesView/BaselinesView.tsx               L220   t(         setDiffError(t("baselines.compareSelectBoth", "Select two baselines."));
components/BaselinesView/BaselinesView.tsx               L225   t(         t("baselines.compareSameBaseline", "Select two different baselines.")
components/BaselinesView/BaselinesView.tsx               L330   t(         summary={t("baselines.summary", { count: state.baselines.length })}
components/CsvImport/CsvImport.tsx                       L252   t(         err instanceof Error ? err.message : t("export.errorGeneric", "Export failed")
components/CsvImport/CsvImport.tsx                       L270   t(         err instanceof Error ? err.message : t("export.errorGeneric", "Export failed")
components/CsvImport/CsvImport.tsx                       L432   t(         {t("import.previewEmptyTitleRows", {
components/CsvImport/CsvImport.tsx                       L591   t(         {t("import.nothingWritten", { count: result.skipped_count })}
components/CsvImport/CsvImport.tsx                       L620   t(         : t("import.moreErrors", {
components/CsvImport/CsvImport.tsx                       L786   t(         <h2 className={styles.sectionHeading}>{t("export.title", "CSV Export")}</h2>
components/CsvImport/CsvImport.tsx                       L789   t(         <h3 className={styles.cardTitle}>{t("export.entityType", "Entity Type")}</h3>
components/DiagramView/DiagramView.tsx                   L77    t(         summary={t("diagrams.summary", { count: items.length })}
components/GlossaryView/GlossaryView.tsx                 L751   t(         summary={t("glossary.summary", { count: terms.length, defaultValue: "{{count}} Begriffe" })}
components/Goals/GoalsPage.tsx                           L146   t(         t("goals.summary", { count: goals.length, defaultValue: `${goals.length} Ziele` }),
components/IcdView/IcdDetailPane.tsx                     L461   t(         {t("icds.similarInterfaces", "Similar Interfaces")}
components/IcdView/IcdView.tsx                           L303   t(         summary={t("icds.summary", { count: icds.length })}
components/IcdView/SimilarIcdsPanel.tsx                  L67    t(         {t("icds.similar.heading", "Similar ICDs")}
components/IcdView/SimilarIcdsPanel.tsx                  L78    t(         : t("icds.similar.findButton", "Find Similar")}
components/IcdView/SimilarIcdsPanel.tsx                  L121   t(         {t("icds.similar.empty", "No similar ICDs found.")}
components/InterviewEditors/InterviewEditors.tsx         L114   t(         summary={t("interviews.summary", { count: items.length })}
components/NavigationShell/SidebarNavigation.tsx         L595   t(         ? t("nav.showOptionalArtifacts", "Optionale Artefakte einblenden")
components/NavigationShell/SidebarNavigation.tsx         L596   t(         : t("nav.hideOptionalArtifacts", "Optionale Artefakte ausblenden")
components/NeedsEditors/NeedsEditors.tsx                 L316   t(         t('needs.summary', { count: needs.length, defaultValue: `${needs.length}` }),
components/PermissionMatrix/PermissionMatrixEditor.tsx   L103   t(         {t("permissionMatrix.capability." + cap)}
components/SystemSettings/EnforcementModePanel.tsx       L126   t(         {t("systemSettings.enforcementMode.meta", {
components/SystemSettings/PermissionDefaultsTab.tsx      L71    t(         t("systemSettings.permissionDefaults.propagatedToast", { count: n })
components/TestRuns/TestRunsList.tsx                     L185   t(         summary={t("testRuns.summary", { count: items.length })}
components/TestRuns/TestRunsList.tsx                     L248   t(         {t("editor.name", "Name")} *
components/UserProfileSettings/ApiKeysSection.tsx        L123   t(         {t("apiKeys.createNew", "Neuen Token erstellen")}
components/UserProfileSettings/ProfileSection.tsx        L85    t(         <h3 className={styles.heading}>{t("profile.nameHeading", "Name")}</h3>
components/UserProfileSettings/ProfileSection.tsx        L102   t(         {t("profile.saved", "Profil gespeichert")}
components/UserProfileSettings/ProfileSection.tsx        L109   t(         {displayName || t("profile.noName", "Kein Name hinterlegt")}
components/UserProfileSettings/ProfileSection.tsx        L117   t(         {t("profile.edit", "Bearbeiten")}
components/UserProfileSettings/ProfileSection.tsx        L124   t(         {t("profile.firstName", "Vorname")}
components/UserProfileSettings/ProfileSection.tsx        L139   t(         {t("profile.lastName", "Nachname")}
components/UserProfileSettings/ProfileSection.tsx        L165   t(         {isSaving ? t("profile.saving", "Speichern…") : t("profile.save", "Speichern")}
components/UserProfileSettings/ProfileSection.tsx        L174   t(         {t("profile.cancel", "Abbrechen")}
components/UserProfileSettings/UserProfileSettings.tsx   L106   t(         <h3 className={styles.visibilityHeading}>{t("settings.visibility", "Sichtbarkeit")} (Workspace: {activeWorkspa
components/UserProfileSettings/UserProfileSettings.tsx   L155   t(         : t("settings.visibilityFromPreset", "(aus Preset)")}
components/WorkflowEditor/EntityTypeSelector.tsx         L51    t(         : t("workflow.entitySelector.stateCount", { count });
components/WorkflowEditor/WorkflowEditorPage.tsx         L124   t(         flashToast(t("workflow.toast.propagated", { count }));
components/WorkspaceSettings/AiPromptsSection.tsx        L328   t(         {isBusy ? t("saving", "Saving...") : t("save", "Save")}
components/WorkspaceSettings/LlmSettingsSection.tsx      L114   t(         <h3 className={styles.heading}>{t("settings.llm.title", "LLM Provider")}</h3>
components/WorkspaceSettings/LlmSettingsSection.tsx      L122   t(         <h3 className={styles.heading}>{t("settings.llm.title", "LLM Provider")}</h3>
components/WorkspaceSettings/LlmSettingsSection.tsx      L131   t(         {t("settings.llm.provider", "Provider")}
components/WorkspaceSettings/LlmSettingsSection.tsx      L179   t(         {t("settings.llm.baseUrl", "Base URL")}
components/WorkspaceSettings/LlmSettingsSection.tsx      L194   t(         {t("settings.llm.apiKey", "API Key")}
components/WorkspaceSettings/LlmSettingsSection.tsx      L205   t(         : t("settings.llm.apiKeyNotSet", "Not set")
components/WorkspaceSettings/LlmSettingsSection.tsx      L211   t(         {t("settings.llm.modelName", "Model Name")}
components/WorkspaceSettings/LlmSettingsSection.tsx      L248   t(         {isSaving ? t("saving", "Saving...") : t("save", "Save")}
components/WorkspaceSettings/PermissionsSection.tsx      L178   t(         setError(t("permissions.userRequired", "User ID is required."));
components/WorkspaceSettings/PermissionsSection.tsx      L358   t(         {t("permissions.title", "Item Permissions")}
components/WorkspaceSettings/PermissionsSection.tsx      L462   t(         ? t("permissions.noMembers", "No workspace members")
components/WorkspaceSettings/PermissionsSection.tsx      L463   t(         : t("permissions.selectUser", "Select a member…")}
components/WorkspaceSettings/PermissionsSection.tsx      L479   t(         {t("permissions.workspaceWide", "Workspace-wide (all artifacts)")}
components/WorkspaceSettings/PermissionsSection.tsx      L507   t(         {isGranting ? "…" : `+ ${t("permissions.grant", "Grant")}`}
components/WorkspaceSettings/PermissionsSection.tsx      L526   t(         ? t("permissions.noMembers", "No workspace members")
components/WorkspaceSettings/PermissionsSection.tsx      L527   t(         : t("permissions.filterSelect", "Show rules for member…")}
components/WorkspaceSettings/PermissionsSection.tsx      L542   t(         {isLoading ? "…" : t("permissions.load", "Load rules")}
components/WorkspaceSettings/PermissionsSection.tsx      L561   t(         {t("permissions.empty", "No permission rules for this user.")}
components/WorkspaceSettings/PermissionsSection.tsx      L569   t(         <th className={styles.th}>{t("permissions.user", "User")}</th>
components/WorkspaceSettings/PermissionsSection.tsx      L570   t(         <th className={styles.th}>{t("permissions.artifact", "Artifact")}</th>
components/WorkspaceSettings/PermissionsSection.tsx      L571   t(         <th className={styles.th}>{t("permissions.level", "Level")}</th>
components/WorkspaceSettings/PermissionsSection.tsx      L585   t(         : t("permissions.workspaceWideShort", "workspace-wide")}
components/WorkspaceSettings/PromptVariablesSection.tsx  L507   t(         {t("save", "Save")}
components/WorkspaceSettings/WorkflowPermissionsSection.tsx L234   t(         {t("settings.workflowConfig", "Workflow Configuration")}
components/WorkspaceSettings/WorkflowPermissionsSection.tsx L276   t(         {t("settings.openInEditor", "Open in Workflow Editor")}
components/WorkspaceSettings/WorkflowPermissionsSection.tsx L304   t(         {t("settings.permissionConfig", "Permission Configuration")}
components/WorkspaceSettings/WorkflowPermissionsSection.tsx L351   t(         : t("settings.overrideMatrix", "Override matrix…")}
components/WorkspaceSettings/WorkspaceSettings.tsx       L247   t(         {t("settings.adminOnly", "You must be an admin to view or edit Workspace Settings. Please visit the Profile di
components/WorkspaceSettings/WorkspaceSettings.tsx       L314   t(         <h3 id="workspace-name-heading" className={styles.heading}>{t("settings.workspaceName", "Workspace Name")}</h3
components/WorkspaceSettings/WorkspaceSettings.tsx       L397   t(         {profile === "dev_mode" ? t("settings.devModeHint", "Feature / Story / Task") : t("settings.seModeHint", "Syst
components/WorkspaceSettings/WorkspaceSettings.tsx       L453   t(         {t("settings.csvImport", "CSV-Import")}
components/WorkspaceSettings/WorkspaceSettings.tsx       L537   t(         <h3 className={styles.heading}>{t("settings.traceability", "Traceability")}</h3>
components/WorkspaceSettings/WorkspaceSettings.tsx       L543   t(         {t("settings.decompositionLinkType", "Decomposition Link Typ")}
components/WorkspaceSettings/WorkspaceSettings.tsx       L573   t(         {t("settings.defaultLinkType", "Standard-Linktyp")}
components/canvas/CanvasEditor.tsx                       L645   t(         const textbox = new fabric.Textbox(t("canvas.defaultText", "Text"), {
components/canvas/CanvasEditor.tsx                       L811   t(         label = new fabric.Textbox(t("canvas.defaultLabel", "Label"), {
components/canvas/CanvasEditor.tsx                       L1193  t(         {toolButton("rect", ICONS.rect, t("canvas.toolbar.rect", "Component (Rectangle)"), styles.shapeTool)}
components/canvas/CanvasEditor.tsx                       L1194  t(         {toolButton("ellipse", ICONS.ellipse, t("canvas.toolbar.ellipse", "Node (Ellipse)"), styles.shapeTool)}
components/canvas/CanvasEditor.tsx                       L1195  t(         {toolButton("text", ICONS.text, t("canvas.toolbar.text", "Text"), styles.shapeTool)}
components/canvas/CanvasEditor.tsx                       L1203  t(         t("canvas.toolbar.connector", "Trace — drag from one node to another"),
components/canvas/CanvasEditor.tsx                       L1211  t(         title={t("canvas.toolbar.lineStyle", "Trace style (solid / dashed)")}
components/canvas/CanvasEditor.tsx                       L1212  t(         aria-label={t("canvas.toolbar.lineStyle", "Trace style")}
components/canvas/CanvasEditor.tsx                       L1245  t(         <span className={styles.groupLabel}>{t("canvas.toolbar.fill", "Fill")}</span>
components/canvas/CanvasEditor.tsx                       L1256  t(         title={c === "transparent" ? t("canvas.toolbar.noFill", "No fill") : `Fill ${c}`}
components/canvas/CanvasEditor.tsx                       L1287  t(         title={t("canvas.toolbar.snap", "Snap to grid")}
components/canvas/CanvasEditor.tsx                       L1288  t(         aria-label={t("canvas.toolbar.snap", "Snap to grid")}
components/canvas/CanvasEditor.tsx                       L1298  t(         title={t("canvas.toolbar.zoomOut", "Zoom out")}
components/canvas/CanvasEditor.tsx                       L1299  t(         aria-label={t("canvas.toolbar.zoomOut", "Zoom out")}
components/canvas/CanvasEditor.tsx                       L1311  t(         title={t("canvas.toolbar.zoomIn", "Zoom in")}
components/canvas/CanvasEditor.tsx                       L1312  t(         aria-label={t("canvas.toolbar.zoomIn", "Zoom in")}
components/canvas/CanvasEditor.tsx                       L1321  t(         title={t("canvas.toolbar.zoomFit", "Fit content")}
components/canvas/CanvasEditor.tsx                       L1322  t(         aria-label={t("canvas.toolbar.zoomFit", "Fit content")}
components/shared/TraceLinkPanel.tsx                     L237   t(         {t("actions.newLink", "Neuen Link erstellen")}
components/shared/TraceLinkPanel.tsx                     L244   t(         {t("actions.showAll", "Alle anzeigen")}
components/shared/TraceSpine/TraceSpine.tsx              L198   t(         title={t("traceSpine.stationCount", {
```

## 4. Tote Locale-Keys (in de/en vorhanden, im Code nirgends referenziert)

Hinweis: Keys, die ueber dynamische t()-Keys erreichbar sind, koennen hier erscheinen.
Fuer die Top-Namespaces (attributes, arch, settings, risks, admin) ist das ausgeschlossen -
es existiert keine dynamische Aufrufstelle in diesen Namespaces.

=== DEAD KEYS count=536 ===
  ns attributes                     44
  ns arch                           33
  ns settings                       27
  ns risks                          21
  ns admin                          17
  ns testRuns                       17
  ns diagramGraph                   16
  ns nav                            16
  ns workflow                       15
  ns editor                         14
  ns systemHealth                   13
  ns traceability                   13
  ns metrics                        11
  ns systemSettings                 11
  ns testcases                      11
  ns archLegend                     10
  ns diagrams                       10
  ns icds                           10
  ns import                         10
  ns interviews                     10
  ns sections                       10
  ns sidebar                        10
  ns adrs                           9
  ns issues                         9
  ns reviews                        9
  ns traceSpine                     9
  ns workspaceCreate                9
  ns artifactForm                   8
  ns categories                     8
  ns glossary                       8
  ns interview                      8
  ns audit                          7
  ns baselines                      7
  ns createTraceLinkDialog          7
  ns needs                          7
  ns adr                            6
  ns goals                          6
  ns memory                         6
  ns permissionMatrix               6
  ns reqTypeShort                   6
  ns req                            5
  ns reqType                        5
  ns verificationMethod             5
  ns banners                        4
  ns linkType                       4
  ns reqLevel                       4
  ns actions                        3
  ns customFields                   3
  ns errors                         3
  ns search                         3
  ns apiKeys                        2
  ns app                            2
  ns bundleExport                   2
  ns notifications                  2
  ns adminOps                       1
  ns archDecompose                  1
  ns dashboard                      1
  ns deriveTestcase                 1
  ns tracelinks                     1
   actions.clear
   actions.confirmDelete
   actions.deleteConfirmPrompt
   admin.attributeVisibility
   admin.attributeVisibilityDescription
   admin.attributeVisibilityEmpty
   admin.entityType.adr
   admin.entityType.architectureElement
   admin.entityType.issue
   admin.entityType.requirement
   admin.entityType.risk
   admin.entityType.stakeholderNeed
   admin.entityType.testCase
   admin.entityTypeLabel
   admin.required
   admin.requiredFieldLabel
   admin.saved
   admin.visible
   admin.visibleFieldLabel
   admin.visibleFields
   adminOps.restoringNow
   adr.context
   adr.contextPlaceholder
   adr.decision
   adr.decisionPlaceholder
   adr.status
   adr.titlePlaceholder
   adrs.consequences
   adrs.context
   adrs.deleteConfirm
   adrs.deleteFailed
   adrs.deleteTitle
   adrs.saveFailed
   adrs.summary_one
   adrs.summary_other
   adrs.titlePlaceholder
   apiKeys.name
   apiKeys.status
   app.placeholder
   app.title
   arch.deleteConfirm
   arch.elementType.component
   arch.elementType.interface
   arch.elementType.layer
   arch.elementType.module
   arch.elementType.subsystem
   arch.level
   arch.levelAutoCalculated
   arch.levelHint
   arch.linkedRequirements
   arch.noParent
   arch.parentElement
   arch.roleHint
   arch.roleValue.component
   arch.roleValue.subsystem
   arch.roleValue.system
   arch.summary_one
   arch.summary_other
   arch.tree.addChild
   arch.tree.allLevels
   arch.tree.allTypes
   arch.tree.collapse
   arch.tree.edit
   arch.tree.expand
   arch.tree.filteredCount
   arch.tree.linkRequirement
   arch.tree.noMatches
   arch.tree.searchPlaceholder
   arch.tree.showDetails
   arch.tree.sortDefault
   arch.tree.sortLabel
   arch.tree.sortTitleAsc
   arch.tree.sortUpdatedDesc
   archDecompose.close
   archLegend.statusApproved
   archLegend.statusApprovedMeaning
   archLegend.statusDraft
   archLegend.statusDraftMeaning
   archLegend.statusOutdated
   archLegend.statusOutdatedMeaning
   archLegend.statusRejected
   archLegend.statusRejectedMeaning
   archLegend.statusReview
   archLegend.statusReviewMeaning
   artifactForm.collapseSection
   artifactForm.expandSection
   artifactForm.field.consequences
   artifactForm.field.context
   artifactForm.field.description
   artifactForm.lockedHint
   artifactForm.saveFailed
   artifactForm.unsavedChanges
   attributes.catalog.onCollision.overwrite
   attributes.catalog.onCollision.rename
   attributes.catalog.onCollision.skip
   attributes.entityTypes.Adr
   attributes.entityTypes.ArchitectureElement
   attributes.entityTypes.ChangeRequest
   attributes.entityTypes.GlossaryTerm
   attributes.entityTypes.Goal
   attributes.entityTypes.Icd
   attributes.entityTypes.Issue
   attributes.entityTypes.Requirement
   attributes.entityTypes.Risk
   attributes.entityTypes.StakeholderNeed
   attributes.entityTypes.TestCase
   attributes.import.onCollision.overwrite
   attributes.import.onCollision.rename
   attributes.import.onCollision.skip
   attributes.layout.spacer.lg
   attributes.layout.spacer.md
   attributes.layout.spacer.sm
   attributes.layout.span_full
   attributes.layout.span_half
   attributes.layout.span_quarter
   attributes.table.audience
   attributes.table.name
   attributes.table.origin.global
   attributes.table.origin.global_customized
   attributes.table.origin.workspace_only
   attributes.table.originHeader
   attributes.table.required
   attributes.table.section
   attributes.table.type
   attributes.table.visible
   attributes.types.actor
   attributes.types.boolean
   attributes.types.date
   attributes.types.enum
   attributes.types.multi-enum
   attributes.types.number
   attributes.types.reference
   attributes.types.text
   attributes.types.textarea
   attributes.types.user
   attributes.types.widget
   audit.scope.document
   audit.scope.global
   audit.scope.project
   audit.severity.blocker
   audit.severity.warning
   audit.waivers.state.active
   audit.waivers.state.expired
   banners.level.critical
   banners.level.info
   banners.level.neutral
   banners.level.warning
   baselines.empty
   baselines.placeholder
   baselines.scopeDocument
   baselines.scopeGlobal
   baselines.scopeProject
   baselines.summary_one
   baselines.summary_other
   bundleExport.close
   bundleExport.error
   categories.api
   categories.data
   categories.functional
   categories.integration
   categories.non-functional
   categories.stakeholder
   categories.test
   categories.ui-ux
   createTraceLinkDialog.typeAdr
   createTraceLinkDialog.typeAll
   createTraceLinkDialog.typeArchitecture
   createTraceLinkDialog.typeIssue
   createTraceLinkDialog.typeRequirement
   createTraceLinkDialog.typeRisk
   createTraceLinkDialog.typeTestCase
   customFields.noSelection
   customFields.saveValues
   customFields.workspaceSection
   dashboard.preset
   deriveTestcase.close
   diagramGraph.accents.danger
   diagramGraph.accents.default
   diagramGraph.accents.muted
   diagramGraph.accents.primary
   diagramGraph.accents.success
   diagramGraph.accents.warning
   diagramGraph.edgeTypes.association
   diagramGraph.edgeTypes.containment
   diagramGraph.edgeTypes.dependency
   diagramGraph.edgeTypes.flow
   diagramGraph.nodeTypes.box
   diagramGraph.nodeTypes.diamond
   diagramGraph.nodeTypes.ellipse
   diagramGraph.nodeTypes.group
   diagramGraph.nodeTypes.note
   diagramGraph.nodeTypes.rounded
   diagrams.noItems
   diagrams.noTraceLinks
   diagrams.summary_one
   diagrams.summary_other
   diagrams.traceability
   diagrams.typeLabels.block
   diagrams.typeLabels.canvas
   diagrams.typeLabels.context
   diagrams.typeLabels.flow
   diagrams.typeLabels.mermaid
   editor.acceptanceCriteria
   editor.acceptanceCriteriaPlaceholder
   editor.deleteConfirm
   editor.exportPdf
   editor.levelUnset
   editor.moscowPriority
   editor.moscowPriorityRequired
   editor.selectPriority
   editor.selectVerificationMethod
   editor.status
   editor.titleRequired
   editor.type
   editor.verificationMethodRequired
   editor.workflowState
   errors.llm_not_configured
   errors.not_found
   errors.unauthorized
   glossary.definitionRequired
   glossary.lifecycleStatus.active
   glossary.lifecycleStatus.deprecated
   glossary.lifecycleStatus.outdated
   glossary.newTerm
   glossary.summary_one
   glossary.summary_other
   glossary.termRequired
   goals.mainGoalDraft
   goals.summary_one
   goals.summary_other
   goals.transition.Archiviert
   goals.transition.Entwurf
   goals.transition.Freigegeben
   icds.currentVersion
   icds.empty
   icds.interfaceTypePlaceholder
   icds.loadFailed
   icds.noArtifacts
   icds.noTraceLinks
   icds.summary_one
   icds.summary_other
   icds.traceability
   icds.versions
   import.failed
   import.moreErrors_one
   import.moreErrors_other
   import.nothingWritten_one
   import.nothingWritten_other
   import.previewEmptyTitleRows_one
   import.previewEmptyTitleRows_other
   import.statusValue.ok
   import.statusValue.rollback
   import.statusValue.validation_error
   interview.start.Adr
   interview.start.ArchitectureElement
   interview.start.Goal
   interview.start.Issue
   interview.start.Requirement
   interview.start.Risk
   interview.start.StakeholderNeed
   interview.start.TestCase
   interviews.forType.Adr
   interviews.forType.ArchitectureElement
   interviews.forType.Goal
   interviews.forType.Issue
   interviews.forType.Requirement
   interviews.forType.Risk
   interviews.forType.StakeholderNeed
   interviews.forType.TestCase
   interviews.summary_one
   interviews.summary_other
   issues.category
   issues.deleteConfirm
   issues.deleteFailed
   issues.deleteTitle
   issues.saveFailed
   issues.severity
   issues.summary_one
   issues.summary_other
   issues.tags
   linkType.suspectRuleValues.none
   linkType.suspectRuleValues.parent_change_flags_children
   linkType.suspectRuleValues.source_change_flags_target
   linkType.suspectRuleValues.target_change_flags_source
   memory.scope.user
   memory.summary_one
   memory.summary_other
   memory.tab.artifact
   memory.tab.user
   memory.tab.workspace
   metrics.help.coverage
   metrics.help.openRisks
   metrics.help.openRisksCritical
   metrics.help.volatility
   metrics.help.workflowGap
   metrics.openRisksCritical
   metrics.status.critical
   metrics.status.healthy
   metrics.status.neutral
   metrics.status.warning
   metrics.traceDensity
   nav.audit
   nav.bauhausTheme
   nav.diagrams
   nav.groupAdmin
   nav.groupArchitecture
   nav.groupOverview
   nav.groupRequirements
   nav.groupTest
   nav.icds
   nav.import
   nav.memory
   nav.metrics
   nav.nordicTheme
   nav.sepiaTheme
   nav.tests
   nav.workflows
   needs.deleteConfirm
   needs.deleteFailed
   needs.deleteTitle
   needs.deriveStarted
   needs.saveFailed
   needs.summary_one
   needs.summary_other
   notifications.unread_one
   notifications.unread_other
   permissionMatrix.capability.assign_role
   permissionMatrix.capability.read
   permissionMatrix.capability.workflow_approval
   permissionMatrix.capability.workflow_transition
   permissionMatrix.capability.workspace_config
   permissionMatrix.capability.write
   req.acceptanceCriteriaRequired
   req.changeReasonPlaceholderArchitecture
   req.section.changeControl
   req.section.classificationProperties
   req.section.generalInformation
   reqLevel.L1
   reqLevel.L2
   reqLevel.L3
   reqLevel.L4
   reqType.FeatureReq
   reqType.HWReq
   reqType.SWReq
   reqType.StReq
   reqType.UseCase
   reqTypeShort.FeatureReq
   reqTypeShort.HWReq
   reqTypeShort.SWReq
   reqTypeShort.StReq
   reqTypeShort.SyReq
   reqTypeShort.UseCase
   reviews.type.adr
   reviews.type.architecture
   reviews.type.glossary
   reviews.type.icd
   reviews.type.issue
   reviews.type.need
   reviews.type.requirement
   reviews.type.risk
   reviews.type.test-case
   risks.category
   risks.computedScores
   risks.deleteConfirm
   risks.deleteFailed
   risks.deleteTitle
   risks.impact
   risks.level.high
   risks.level.low
   risks.level.medium
   risks.matrixTitle
   risks.mitigationStrategy
   risks.owner
   risks.probability
   risks.riskScoreLabel
   risks.rpnHint
   risks.rpnLabel
   risks.saveFailed
   risks.score
   risks.severity
   risks.summary_one
   risks.summary_other
   search.loading
   search.noResults
   search.placeholder
   sections.attribution
   sections.change_control
   sections.classification
   sections.content
   sections.custom
   sections.general
   sections.identification
   sections.traceability
   sections.type_specific
   sections.verification
   settings.attributeVisibility
   settings.attributeVisibilityHint
   settings.customFields.deleteConfirmMessage
   settings.customFields.deleteConfirmTitle
   settings.customFields.description
   settings.customFields.empty
   settings.customFields.name
   settings.customFields.options
   settings.customFields.optionsHint
   settings.customFields.required
   settings.customFields.title
   settings.customFields.type
   settings.dataManagementHint
   settings.promptTemplates.slot.architecture_to_risk
   settings.promptTemplates.slot.decision_to_adr
   settings.promptTemplates.slot.goal_aggregate
   settings.promptTemplates.slot.need_to_sysreq
   settings.promptTemplates.slot.sysreq_decompose_next_level
   settings.promptTemplates.slot.sysreq_to_arch_assign
   settings.promptTemplates.slot.testcase_derive
   settings.promptTemplates.slot.workspace_to_glossary
   settings.tabs.visibility
   settings.userManagement.createFailed
   settings.userManagement.lastAdminError
   settings.workspaceClosed
   settings.workspaceDeleted
   settings.workspaceReactivated
   sidebar.diff.empty
   sidebar.diff.error
   sidebar.diff.from
   sidebar.diff.to
   sidebar.inspector.refresh
   sidebar.inspector.skeletonLoading
   sidebar.trace.create
   sidebar.trace.viewAll
   sidebar.version.copied
   sidebar.version.menu.copy
   systemHealth.componentNames.celery_beat
   systemHealth.componentNames.celery_worker
   systemHealth.componentNames.database
   systemHealth.componentNames.llm_provider
   systemHealth.componentNames.mcp_server
   systemHealth.componentNames.memory_backend
   systemHealth.componentNames.memory_embedding
   systemHealth.componentNames.redis
   systemHealth.status.degraded
   systemHealth.status.down
   systemHealth.status.ok
   systemHealth.status.unknown
   systemHealth.versionBuiltAt
   systemSettings.enforcementFlip.acknowledgeLabel_one
   systemSettings.enforcementFlip.acknowledgeLabel_other
   systemSettings.enforcementFlip.message_one
   systemSettings.enforcementFlip.message_other
   systemSettings.enforcementFlip.viewMismatches_one
   systemSettings.enforcementFlip.viewMismatches_other
   systemSettings.enforcementMode.meta_one
   systemSettings.enforcementMode.meta_other
   systemSettings.permissionDefaults.propagatedToast_one
   systemSettings.permissionDefaults.propagatedToast_other
   systemSettings.themes.export
   testRuns.closeConfirm
   testRuns.detailLoadFailed
   testRuns.empty
   testRuns.loadFailed
   testRuns.namePlaceholder
   testRuns.resultEntry.status.blocked
   testRuns.resultEntry.status.failed
   testRuns.resultEntry.status.not_run
   testRuns.resultEntry.status.passed
   testRuns.status.closed
   testRuns.status.failed
   testRuns.status.in_progress
   testRuns.status.partial
   testRuns.status.passed
   testRuns.summary_one
   testRuns.summary_other
   testRuns.testCaseOptionsLoadFailed
   testcases.deleteFailed
   testcases.deleteTitle
   testcases.saveFailed
   testcases.summary_one
   testcases.summary_other
   testcases.testType.analysis
   testcases.testType.demonstration
   testcases.testType.inspection
   testcases.testType.integration
   testcases.testType.system
   testcases.testType.unit
   traceSpine.derived
   traceSpine.emptyHint
   traceSpine.error
   traceSpine.origin
   traceSpine.stationCount_one
   traceSpine.stationCount_other
   traceSpine.stationOpen
   traceSpine.verification_one
   traceSpine.verification_other
   traceability.impactDepth
   traceability.impactDirBoth
   traceability.impactDirIncoming
   traceability.impactDirOutgoing
   traceability.impactDirection
   traceability.impactEmpty
   traceability.impactRunning
   traceability.pendingAiReview_one
   traceability.pendingAiReview_other
   traceability.placeholder
   traceability.seModeHint
   traceability.seNoValidType
   traceability.testCasesGroup
   tracelinks.empty
   verificationMethod.Analysis
   verificationMethod.Demonstration
   verificationMethod.Inspection
   verificationMethod.Review
   verificationMethod.Test
   workflow.entitySelector.stateCount_one
   workflow.entitySelector.stateCount_other
   workflow.entityTypes.Adr
   workflow.entityTypes.ArchitectureElement
   workflow.entityTypes.Goal
   workflow.entityTypes.Issue
   workflow.entityTypes.MainGoal
   workflow.entityTypes.Requirement
   workflow.entityTypes.Risk
   workflow.entityTypes.StakeholderNeed
   workflow.entityTypes.TestCase
   workflow.modal.closeDialog
   workflow.proposal.selectAll
   workflow.toast.propagated_one
   workflow.toast.propagated_other
   workspaceCreate.languageDe
   workspaceCreate.languageEn
   workspaceCreate.nameLabel
   workspaceCreate.presetExtended
   workspaceCreate.presetMinimal
   workspaceCreate.presetStandard
   workspaceCreate.terminologyDevMode
   workspaceCreate.terminologyLabel
   workspaceCreate.terminologySeMode
```

## 5. Dynamische t()-Keys (nur zur Laufzeit aufloesbar)

Template-Literal-Keys und Variable-Keys, die ein statischer Scan nicht abdecken kann.

=== count-bearing t() keys: 0 ===
=== template-literal t() keys: 60 ===
  components/AdminDialog/SystemHealthDialog.tsx        L233   {t(`systemHealth.componentNames.${component.name}`, component.name)}
  components/AdminDialog/SystemHealthDialog.tsx        L244   {t(`systemHealth.status.${component.status}`, component.status)}
  components/ArchitectureEditors/ArchitectureEditors.tsx L467   label: t(`arch.lifecycleStatus.${s}`, s),
  components/AttributeEditor/AttributeCatalogDialog.tsx L122   itemType: t(`attributes.entityTypes.${itemType}`, { defaultValue: itemType }),
  components/AttributeEditor/AttributeCatalogDialog.tsx L267   {t(`attributes.catalog.onCollision.${choice}`)}
  components/AttributeEditor/AttributeCreateDialog.tsx L180   {t(`attributes.types.${option}`, { defaultValue: option })}
  components/AttributeEditor/AttributeEditorPage.tsx   L678   {t(`attributes.entityTypes.${type}`, { defaultValue: type })}
  components/AttributeEditor/AttributeImportDialog.tsx L96    {t(`attributes.import.onCollision.${choice}`)}
  components/AttributeEditor/AttributeList.tsx         L125   <h3>{t(`sections.${section}`, { defaultValue: section })}</h3>
  components/AttributeEditor/AttributeList.tsx         L242   {t(`attributes.table.origin.${origin}`)}
  components/AttributeEditor/AttributeTable.tsx        L120   {t(`attributes.types.${attribute.type}`, { defaultValue: attribute.type })}
  components/AttributeEditor/AttributeTable.tsx        L136   {t(`attributes.table.origin.${origin}`)}
  components/AttributeEditor/LayoutFlowEditor.tsx      L96    <span>{t(`sections.${token.name}`, { defaultValue: token.name })}</span>
  components/AttributeEditor/LayoutFlowEditor.tsx      L113   {t(`attributes.layout.spacer.${size}`)}
  components/AttributeEditor/LayoutFlowEditor.tsx      L187   {t(`sections.${name}`, { defaultValue: name })}
  components/AttributeEditor/LayoutFlowEditor.tsx      L222   {t(`attributes.layout.span_${span}`)}
  components/AttributeEditor/LayoutFlowEditor.tsx      L243   {t(`attributes.layout.spacer.${size}`)}
  components/Audit/audit-dashboard.tsx                 L701   {t(`audit.scope.${s}`, s)}
  components/Audit/audit-dashboard.tsx                 L837   {t(`audit.waivers.state.${w.state}`, w.state)}
  components/Audit/audit-dashboard.tsx                 L1151  {t(`audit.severity.${finding.severity}`, finding.severity)}
  components/CsvImport/CsvImport.tsx                   L576   {t("import.statusLabel")}: {t(`import.statusValue.${result.status}`)}
  components/DiagramGraphEditor/GraphInspectorPanel.tsx L163   {t(`diagramGraph.nodeTypes.${tp}`)}
  components/DiagramGraphEditor/GraphInspectorPanel.tsx L179   {t(`diagramGraph.accents.${accent}`)}
  components/DiagramGraphEditor/GraphInspectorPanel.tsx L383   {t(`diagramGraph.edgeTypes.${tp}`)}
  components/DiagramView/DiagramCreateForm.tsx         L108   {t(`diagrams.typeLabels.${tp}`, tp)}
  components/DiagramView/DiagramList.tsx               L139   options: DIAGRAM_TYPES.map((tp: DiagramType) => ({ value: tp, label: t(`diagrams.typeLabels.${tp}`, 
  components/DiagramView/DiagramList.tsx               L176   : t(`diagrams.typeLabels.${group.key}`, group.key);
  components/GlossaryView/GlossaryView.tsx             L404   label: t(`glossary.lifecycleStatus.${s}`, s),
  components/Goals/GoalDetail.tsx                      L184   {t(`goals.transition.${transition.target_state}`, {
  components/Goals/GoalDetail.tsx                      L197   {t(`goals.transition.${transition.target_state}`, {
  components/Goals/MainGoalPanel.tsx                   L269   ? t(`goals.transition.${archiveTransition.target_state}`, {
  components/InterviewEditors/InterviewDetail.tsx      L73    ? t(`interviews.forType.${artifactType}`, artifactType)
  components/InterviewEditors/InterviewList.tsx        L71    () => visible.map((it) => interviewToNode(it, t(`interviews.forType.${it.artifact_type}`, it.artifac
  components/InterviewEditors/InterviewList.tsx        L150   title={t(`interviews.forType.${session.artifact_type}`, session.artifact_type)}
  components/InterviewWidget/InterviewWidget.tsx       L223   {t(`interview.start.${type}`)}
  components/LinkTypeEditor/LinkTypeEditorPage.tsx     L360   {t(`linkType.suspectRuleValues.${rule}`)}
  components/MetricsDashboard/MetricsDashboard.tsx     L566   helpText={t(`metrics.help.${spec.name}`, METRIC_HELP[spec.name])}
  components/RequirementEditors/RequirementList.tsx    L247   req.type ? t(`reqType.${req.type}`) : undefined,
  components/RequirementEditors/RequirementList.tsx    L248   req.level != null ? t(`reqLevel.L${req.level}`) : undefined,
  components/RequirementEditors/RequirementList.tsx    L249   req.type ? t(`reqTypeShort.${req.type}`) : undefined,
  components/RequirementEditors/RequirementList.tsx    L475   const typeShort = req.type ? t(`reqTypeShort.${req.type}`) : undefined;
  components/RequirementEditors/RequirementList.tsx    L484   ? t(`categories.${req.category}`, { defaultValue: req.category })
  components/RequirementEditors/RequirementList.tsx    L489   value: req.level != null ? t(`reqLevel.L${req.level}`) : null,
  components/RequirementEditors/RequirementList.tsx    L494   ? t(`verificationMethod.${req.verification_method}`, {
  components/RequirementEditors/RequirementList.tsx    L522   ? `${t(`reqLevel.L${req.level}`)} · ${t(`reqType.${req.type}`)}`
  components/RequirementEditors/RequirementList.tsx    L522   ? `${t(`reqLevel.L${req.level}`)} · ${t(`reqType.${req.type}`)}`
  components/RequirementEditors/RequirementList.tsx    L523   : t(`reqType.${req.type}`)
  components/Reviews/ReviewsView.tsx                   L523   {t(`reviews.type.${type}`, toTitleCase(type))}
  components/SystemSettings/BannerSection.tsx          L141   {t(`banners.level.${lvl}`, lvl)}
  components/TestCaseEditors/TestCaseEditors.tsx       L447   {t(`testcases.testType.${type}`, type)}
  components/TestRuns/TestRunsList.tsx                 L214   label: t(`testRuns.status.${s}`, s),
  components/WorkflowEditor/EntityTypeSelector.tsx     L93    label={t(`workflow.entityTypes.${e.type}`)}
  components/WorkflowEditor/StatusBar.tsx              L17    entityType: t(`workflow.entityTypes.${graph.entityType}`),
  components/WorkspaceSettings/WorkspaceBannerSection.tsx L137   {t(`banners.level.${lvl}`, lvl)}
  components/shared/ArtifactForm/ArtifactForm.tsx      L865   {t(`sections.${section.name}`, { defaultValue: section.name })}
  components/shared/ArtifactForm/ArtifactForm.tsx      L875   { section: t(`sections.${section.name}`, { defaultValue: section.name }) }
  components/shared/ArtifactForm/ArtifactForm.tsx      L881   <span>{t(`sections.${section.name}`, { defaultValue: section.name })}</span>
  components/shared/ArtifactForm/widgets/MarkdownTabGroup.tsx L47    {t(`artifactForm.field.${field}`, { defaultValue: field })}
  components/shared/ArtifactForm/widgets/RiskMatrixRpz.tsx L58    <span className={styles.label}>{t(`risks.${field}`)}</span>
  components/shared/ArtifactForm/widgets/RiskMatrixRpz.tsx L68    {t(`risks.level.${level}`)}
=== concatenated t() keys: 0 ===
=== variable t() keys: 16 ===
  components/ArchitectureEditors/ArchitectureLegend.tsx L148   status={t(sample.labelKey, sample.labelDefault)}
  components/ArchitectureEditors/ArchitectureLegend.tsx L153   meaning={t(sample.meaningKey, sample.meaningDefault)}
  components/AttributeEditor/AttributeTable.tsx        L95    {t(column === "origin" ? "attributes.table.originHeader" : `attributes.table.${column}`)}
  components/BaselinesView/BaselinesView.tsx           L366   options: SCOPE_OPTIONS.map((opt) => ({ value: opt.value, label: t(opt.labelKey) })),
  components/BaselinesView/BaselinesView.tsx           L502   <span>{t(opt.labelKey)}</span>
  components/CsvImport/CsvImport.tsx                   L362   {t(ENTITY_TYPE_I18N_KEYS[type] ?? type)}
  components/CsvImport/CsvImport.tsx                   L804   {t(ENTITY_TYPE_I18N_KEYS[type] ?? type)}
  components/Memory/MemoryPage.tsx                     L333   {t(SCOPE_LABEL_KEYS[entry.scope], entry.scope)}
  components/Memory/MemoryPage.tsx                     L422   {t(TAB_LABEL_KEYS[tab], tab)}
  components/MetricsDashboard/MetricsDashboard.tsx     L271   const tileTitle = t(spec.titleKey, spec.name);
  components/MetricsDashboard/MetricsDashboard.tsx     L284   title={t(palette.labelKey, status)}
  components/MetricsDashboard/MetricsDashboard.tsx     L293   aria-label={t(palette.labelKey, status)}
  components/NavigationShell/SidebarNavigation.tsx     L562   {t(NAV_GROUP_LABEL_KEYS[group.id])}
  components/NavigationShell/SidebarNavigation.tsx     L575   {t(item.labelKey)}
  components/shared/ArtifactForm/ArtifactForm.tsx      L1026  {saving ? t("actions.saving") : t(artifactId === null ? "actions.create" : "actions.save")}
  components/shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx L199   {t(TYPE_LABEL_KEYS[key], TYPE_DISPLAY_LABELS[key])}
```
