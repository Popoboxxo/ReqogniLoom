import os
import re
import subprocess
import sys

def verify_req(req_id):
    # Check source code (exclude tests)
    cmd_src = f'git grep -l "{req_id}" -- "backend/**/*.py" "frontend/src/**/*.ts" "frontend/src/**/*.tsx" ":!*/tests/*" ":!*.test.*" ":!*test_*.py" ":!backend/application/tests/*" ":!backend/application/tests/**/*" 2>nul || echo.'
    res_src = subprocess.run(cmd_src, shell=True, capture_output=True, text=True, cwd="c:/Repositories/ai-native-reqflow-POC")
    src_files = [f for f in res_src.stdout.strip().split('\n') if f and f.strip() != '.']
    
    # Check tests
    cmd_test = f'git grep -l "{req_id}" -- "backend/**/test*.py" "backend/**/conftest.py" "frontend/src/**/*.test.ts" "frontend/src/**/*.test.tsx" "e2e/**/*.ts" "backend/application/tests/**/*.py" 2>nul || echo.'
    res_test = subprocess.run(cmd_test, shell=True, capture_output=True, text=True, cwd="c:/Repositories/ai-native-reqflow-POC")
    test_files = [f for f in res_test.stdout.strip().split('\n') if f and f.strip() != '.']
    
    is_implemented = len(src_files) > 0
    is_tested = len(test_files) > 0
    
    state = "Implemented" if is_implemented else "Not Implemented"
    test_status = "Covered" if is_tested else "Missing"
    
    if not is_implemented and not is_tested:
        befunde = "Keine Implementierung oder Tests im Code gefunden."
        remarks = "Sollte implementiert werden."
    elif is_implemented and not is_tested:
        befunde = "Implementierung gefunden, aber keine Tests."
        remarks = "Testabdeckung fehlt."
    elif not is_implemented and is_tested:
        befunde = "Nur Tests gefunden, aber keine Implementierung."
        remarks = "Implementierung prüfen."
    else:
        befunde = "Anforderung ist durch Tests verifiziert und im Code auffindbar."
        remarks = "Regelmäßig auf Regressionen prüfen."
        
    return f"**Implementation State:** {state}\n**Review Findings:** {befunde}\n**Test Status:** {test_status}\n**Remarks:** {remarks}\n"

def update_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by requirement headings
    parts = re.split(r'(### REQ-[A-Z0-9\-]+:.*?\n)', content)
    
    new_parts = [parts[0]]
    
    for i in range(1, len(parts), 2):
        heading = parts[i]
        body = parts[i+1]
        
        req_id_match = re.search(r'### (REQ-[A-Z0-9\-]+):', heading)
        if not req_id_match:
            new_parts.append(heading)
            new_parts.append(body)
            continue
            
        req_id = req_id_match.group(1)
        
        # Remove any existing lines starting with these fields
        body_lines = body.split('\n')
        cleaned_lines = []
        for line in body_lines:
            if line.startswith('**Implementation State:**') or \
               line.startswith('**Review Findings:**') or \
               line.startswith('**Test Status:**') or \
               line.startswith('**Remarks:**'):
                continue
            cleaned_lines.append(line)
            
        # Remove consecutive blank lines
        cleaned_body = '\n'.join(cleaned_lines)
        cleaned_body = re.sub(r'\n{3,}', '\n\n', cleaned_body)
        
        # Generate new fields
        fields_str = verify_req(req_id)
        
        # Insert fields right before **Traceability:** if it exists, else at the end
        if '**Traceability:**' in cleaned_body:
            cleaned_body = cleaned_body.replace('**Traceability:**', fields_str + '\n**Traceability:**')
        else:
            cleaned_body = cleaned_body.rstrip() + '\n\n' + fields_str + '\n'
            
        new_parts.append(heading)
        new_parts.append(cleaned_body)
        
    new_content = ''.join(new_parts)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"Updated {filepath}")

if __name__ == "__main__":
    for f in sys.argv[1:]:
        update_file(f)
