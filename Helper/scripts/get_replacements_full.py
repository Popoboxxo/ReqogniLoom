import glob
import re
import subprocess
import json
import os
import shutil

paths1 = glob.glob('docs/se/L1/Gesamtsystem/L2/IcdManagementSystem/Components/*/*Requirements.md')
paths2 = glob.glob('docs/se/L1/Gesamtsystem/L2/*/*_Requirements.md')
all_paths = list(set(paths1 + paths2))

def parse_file(filepath):
    filepath = os.path.abspath(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    chunks = []
    matches = list(re.finditer(r'###\s+(REQ-[a-zA-Z0-9\-\_]+)[^\n]*\n+', content))
    
    for i in range(len(matches)):
        start = matches[i].start()
        end = matches[i+1].start() if i + 1 < len(matches) else len(content)
        part = content[start:end]
        
        req_id = matches[i].group(1)
        
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
        
        lines = part.split('\n')
        
        desc_lines = []
        prop_idx = -1
        for idx in range(1, len(lines)):
            line = lines[idx]
            if line.startswith('**'):
                prop_idx = idx
                break
            elif line.startswith('---') or line.startswith('###'):
                prop_idx = idx
                break
            else:
                desc_lines.append(line)
        
        if prop_idx == -1:
            prop_idx = len(lines)
            
        filtered_lines = []
        for line in lines[prop_idx:]:
            if line.startswith('**Implementation State:**') or \
               line.startswith('**Review Findings:**') or \
               line.startswith('**Test Status:**') or \
               line.startswith('**Remarks:**'):
                continue
            filtered_lines.append(line)
            
        new_part = lines[0] + '\n' + '\n'.join(desc_lines).strip('\n') + '\n\n' + new_props + '\n\n' + '\n'.join(filtered_lines).lstrip('\n')
        
        # Ensure that we only replace what actually changed, or just replace the whole part
        if new_part != part:
            chunks.append({
                "TargetContent": part,
                "ReplacementContent": new_part,
                "StartLine": 1,
                "EndLine": len(content.split('\n')),
                "AllowMultiple": False
            })
    
    if chunks:
        return {
            "TargetFile": filepath,
            "Instruction": "Update requirement fields correctly, deleting old properties and inserting new ones",
            "Description": "Update implementation state and test status based on codebase search.",
            "ReplacementChunks": chunks
        }
    return None

if os.path.exists('replacements_chunks_full'):
    shutil.rmtree('replacements_chunks_full')
os.makedirs('replacements_chunks_full')

file_idx = 0
for p in all_paths:
    res = parse_file(p)
    if res:
        with open(f'replacements_chunks_full/replacements_{file_idx}.json', 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=2)
        file_idx += 1

print(f"Generated {file_idx} full chunk files")
