import glob
import re
import subprocess
import json
import os

paths1 = glob.glob('docs/se/L1/Gesamtsystem/L2/IcdManagementSystem/Components/*/*Requirements.md')
paths2 = glob.glob('docs/se/L1/Gesamtsystem/L2/*/*_Requirements.md')
all_paths = list(set(paths1 + paths2))

# We need to make sure we don't output TargetContent that is too large.
# Strategy: 2 chunks per requirement.
# Chunk 1: Replace old properties with empty string
# Chunk 2: Insert new properties right below description

def parse_file(filepath):
    filepath = os.path.abspath(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    chunks = []
    
    # regex to find req blocks
    req_pattern = re.compile(r'(###\s+(REQ-[a-zA-Z0-9\-\_]+).*?(?:\n\n|\Z))(.*?(?=\n\n\*\*|\n\n###|\n\n---|(?:\*\*Domain|\*\*Priority|\*\*Implementation State)))(.*?(?=\n\n###|\n\n---|\Z))', re.DOTALL)
    
    # Let's just use re.finditer on the full content
    matches = list(re.finditer(r'###\s+(REQ-[a-zA-Z0-9\-\_]+)[^\n]*\n+', content))
    
    for i in range(len(matches)):
        start = matches[i].start()
        end = matches[i+1].start() if i + 1 < len(matches) else len(content)
        part = content[start:end]
        
        req_id = matches[i].group(1)
        
        # grep for req_id
        cmd = ['git', 'grep', '-l', req_id]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            files = res.stdout.strip().split('\n')
        except:
            files = []
        files = [f for f in files if f and not f.startswith('docs/')]
        test_files = [f for f in files if 'test' in f.lower() or '/tests/' in f]
        src_files = [f for f in files if f not in test_files]
        
        implemented = len(src_files) > 0
        covered = len(test_files) > 0
        
        if implemented and covered:
            imp_state = "Implemented"
            test_state = "Covered"
            rev_find = "Anforderung ist durch Tests verifiziert und im Code auffindbar."
            rem = "Regelmäßig auf Regressionen prüfen."
        elif implemented and not covered:
            imp_state = "Implemented"
            test_state = "Untested"
            rev_find = "Anforderung ist im Code auffindbar, aber Testabdeckung fehlt."
            rem = "Testabdeckung sicherstellen."
        elif not implemented and covered:
            imp_state = "Not Implemented"
            test_state = "Covered"
            rev_find = "Anforderung ist in Tests abgedeckt, aber Implementierung fehlt."
            rem = "Implementierung abschließen."
        else:
            imp_state = "Not Implemented"
            test_state = "Missing"
            rev_find = "Keine Implementierung oder Tests im Code gefunden."
            rem = "Sollte implementiert werden."
            
        new_props = f"**Implementation State:** {imp_state}\n**Review Findings:** {rev_find}\n**Test Status:** {test_state}\n**Remarks:** {rem}"
        
        # Now find the old properties block and the description
        lines = part.split('\n')
        desc_end_idx = -1
        
        for idx in range(1, len(lines)):
            if lines[idx].startswith('**') or lines[idx].startswith('---'):
                desc_end_idx = idx
                break
        
        if desc_end_idx == -1:
            desc_end_idx = len(lines)
            
        description_lines = lines[:desc_end_idx]
        
        # TargetContent 1: The description block
        # We will append the new properties to it
        target_desc = '\n'.join(description_lines)
        # Ensure exact match by using the exact string from the file
        
        replace_desc = target_desc + '\n\n' + new_props
        
        chunks.append({
            "TargetContent": target_desc,
            "ReplacementContent": replace_desc,
            "StartLine": 1,
            "EndLine": len(content.split('\n')),
            "AllowMultiple": False
        })
        
        # Find old properties to remove
        old_props_lines = []
        in_old_props = False
        for idx in range(desc_end_idx, len(lines)):
            line = lines[idx]
            if line.startswith('**Implementation State:**') or \
               line.startswith('**Review Findings:**') or \
               line.startswith('**Test Status:**') or \
               line.startswith('**Remarks:**'):
                old_props_lines.append(line)
        
        if old_props_lines:
            target_old_props = '\n'.join(old_props_lines)
            chunks.append({
                "TargetContent": target_old_props + '\n',
                "ReplacementContent": "",
                "StartLine": 1,
                "EndLine": len(content.split('\n')),
                "AllowMultiple": False
            })
            
    if chunks:
        return {
            "TargetFile": filepath,
            "Instruction": "Update requirement fields",
            "Description": "Update implementation state and test status based on codebase search.",
            "ReplacementChunks": chunks
        }
    return None

import shutil
if os.path.exists('replacements_chunks'):
    shutil.rmtree('replacements_chunks')
os.makedirs('replacements_chunks')

file_idx = 0
for p in all_paths:
    res = parse_file(p)
    if res:
        with open(f'replacements_chunks/replacements_{file_idx}.json', 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=2)
        file_idx += 1

print(f"Generated {file_idx} chunk files")
