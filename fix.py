import os, re
import sys

def main():
    for root, dirs, files in os.walk('frontend/src'):
        for file in files:
            if file.endswith(('.ts', '.tsx')):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                new_content = content
                
                # Fix React imports
                new_content = re.sub(r'import\s+React\s*,\s*\{\s*', 'import { ', new_content)
                new_content = re.sub(r'import\s+React\s+from\s+[\'\"].*?[\'\"];\n', '', new_content)
                
                # Remove unused vars in some known files that failed
                if file == 'TraceabilityPanel.test.tsx':
                    new_content = 'import { describe, it, expect } from "vitest";\n' + new_content
                
                if file == 'RequirementEditors.tsx':
                    new_content = re.sub(r'const isDraggingRef = useRef\(false\);\n', '', new_content)
                    new_content = new_content.replace('import { requirementsApi } from \'../../api/requirements\';\n', '')
                    new_content = new_content.replace('onResize={(_widthPercent, widthPixels) => {', 'onResize={(_widthPercent) => {')
                    new_content = new_content.replace('import type { Requirement, UUID, MoscowPriority, WorkflowDefinition } from \'../../types\';', 'import type { Requirement, WorkflowDefinition } from \'../../types\';')

                if file == 'ModalDialogBase.test.tsx':
                    new_content = new_content.replace('buttonTestIdPrefix: "min",', 'buttonTestIdPrefix: "min", itemCount: 0,')
                    new_content = new_content.replace('import { fireEvent, render, screen, waitFor } from', 'import { render, screen } from')

                if file == 'ArchitectureEditors.test.tsx':
                    new_content = new_content.replace('element_type: "component",', 'element_type: "component" as any,')
                    new_content = new_content.replace('results: [MOCK_ELEMENT],', 'results: [MOCK_ELEMENT as any],')
                    new_content = new_content.replace('results: [],\n      count: 0,\n    });', 'results: [],\n      count: 0,\n    } as any);')
                    new_content = new_content.replace('vi.mocked(architectureApi.get).mockResolvedValue(MOCK_ELEMENT);', 'vi.mocked(architectureApi.get).mockResolvedValue(MOCK_ELEMENT as any);')
                
                if file == 'WorkspaceContext.test.tsx':
                    new_content = new_content.replace('created_at: new Date().toISOString(),', 'is_active: true, closed_at: null, closed_by: null, created_at: new Date().toISOString(),')
                    new_content = new_content.replace('created_at: "",\n      updated_at: "",', 'is_active: true, closed_at: null, closed_by: null, created_at: "",\n      updated_at: "",')

                if file == 'SplitView.tsx':
                    # remove data-testid="splitview-divider" duplicate (it's at line 353 and 329)
                    new_content = new_content.replace('          }}\n          data-testid="splitview-divider"\n        />\n\n        {/* Right Panel */}', '          }}\n        />\n\n        {/* Right Panel */}')
                    new_content = new_content.replace('<T>', '<T extends any>')

                if new_content != content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Fixed {path}")

if __name__ == "__main__":
    main()
