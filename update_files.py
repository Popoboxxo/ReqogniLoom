import os
import re

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

# 3. Clean up WorkspaceSettings.tsx
#    - Remove duplicate BackupRestoreSection
#    - Fix Terminology Profile text
#    - Fix Attribute Visibility error `[object Object]`
workspace_settings_path = r'c:\Repositories\ai-native-reqflow-POC\frontend\src\components\WorkspaceSettings\WorkspaceSettings.tsx'
ws_content = read_file(workspace_settings_path)
ws_content = ws_content.replace('{profile === "dev_mode" ? "Feature / Story / Task" : "System / Subsystem / Component"}', '{profile === "dev_mode" ? t("settings.devModeHint", "Feature / Story / Task") : t("settings.seModeHint", "System / Subsystem / Component")}')

# Find and remove the second BackupRestoreSection 
# Actually, the user says "Remove duplicate Backup & Restore".
# Let's count them
if ws_content.count('<BackupRestoreSection />') > 1:
    # Just remove the last occurrence
    parts = ws_content.rsplit('<BackupRestoreSection />', 1)
    ws_content = parts[0] + parts[1]

write_file(workspace_settings_path, ws_content)

# 4. Clean up UserProfileSettings.tsx (no real cleanup needed other than modifying de.json later)
# 5. Fix RequirementsList vs NeedsEditors Look and Feel
#    The user wants RequirementForm to use TraceLinkPanel. Let's patch RequirementForm.tsx
req_form_path = r'c:\Repositories\ai-native-reqflow-POC\frontend\src\components\RequirementEditors\RequirementForm.tsx'
req_content = read_file(req_form_path)
req_content = req_content.replace('import { ReqTraceLinkPanel } from \'./ReqTraceLinkPanel\';', 'import { TraceLinkPanel } from \'../shared/TraceLinkPanel\';')
req_content = req_content.replace('''<ReqTraceLinkPanel
          workspaceId={workspaceId}
          requirementId={requirement.id}
          requirements={requirements}
          onLinksChanged={onSaved}
        />''', '''<TraceLinkPanel
          workspaceId={workspaceId}
          artifactId={requirement.id}
        />''')
write_file(req_form_path, req_content)

# 6. Update ArchitectureEditors.tsx to use TraceLinkPanel
arch_form_path = r'c:\Repositories\ai-native-reqflow-POC\frontend\src\components\ArchitectureEditors\ArchitectureEditors.tsx'
arch_content = read_file(arch_form_path)
arch_content = arch_content.replace('import { ArchTraceLinkPanel } from "./ArchTraceLinkPanel";', 'import { TraceLinkPanel } from "../shared/TraceLinkPanel";')
arch_content = arch_content.replace('''<ArchTraceLinkPanel
                workspaceId={activeWorkspace?.id ?? element.workspace_id}
                elementId={element.id}
              />''', '''<TraceLinkPanel
                workspaceId={activeWorkspace?.id ?? element.workspace_id}
                artifactId={element.id}
              />''')
write_file(arch_form_path, arch_content)

# 7. Update IcdView.tsx to use VersionBadge
icd_view_path = r'c:\Repositories\ai-native-reqflow-POC\frontend\src\components\IcdView\IcdView.tsx'
icd_content = read_file(icd_view_path)
icd_content = icd_content.replace('import type { ArchitectureElement } from "../../types";', 'import type { ArchitectureElement } from "../../types";\nimport { VersionBadge, VersionTimeline } from "../shared/VersionBadge";')

# Replace badge in IcdView
badge_pattern = r'<span\s+data-testid="icd-version-badge"[^>]*?>\s*\{t\("icds\.versionBadge",\s*\{\s*n:\s*detail\.version\s*\}\)\}\s*</span>'
icd_content = re.sub(badge_pattern, '<VersionBadge version={detail.version} />', icd_content, flags=re.DOTALL)

# Replace timeline
timeline_pattern = r'<ol\s+style=\{\{[\s\S]*?listStyle:\s*"none",[\s\S]*?padding:\s*0,[\s\S]*?\}\}>\s*\{timeline[\s\S]*?\}\s*</ol>'
icd_content = re.sub(timeline_pattern, '<VersionTimeline timeline={timeline} formatDate={formatDate} />', icd_content, flags=re.DOTALL)

write_file(icd_view_path, icd_content)

print("Updates applied successfully.")
