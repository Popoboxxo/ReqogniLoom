import os
import re
import subprocess
import sys

def check_and_update_dir(target_dir):
    md_files = []
    if os.path.isfile(target_dir):
        if target_dir.endswith('.md'):
            md_files.append(target_dir)
    else:
        for root, _, files in os.walk(target_dir):
            for file in files:
                if file.endswith('.md'):
                    md_files.append(os.path.join(root, file))
                
    for md_file in md_files:
        check_and_update_file(md_file)

def check_and_update_file(md_file):
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Match lines like "### REQ-L1-001:" or "### REQ-L2-WE-001:"
    reqs = list(set(re.findall(r'### (REQ-L\d-[A-Z0-9\-]+)[: \r\n]', content)))
    if not reqs:
        # Some are just REQ-123 or similar?
        reqs = list(set(re.findall(r'### (REQ-[A-Z0-9\-]+)[: \r\n]', content)))
        
    if not reqs:
        return
        
    results = {}
    for req in reqs:
        # Check source code (exclude tests)
        cmd_src = f'git grep -l "{req}" -- "backend/**/*.py" "frontend/src/**/*.ts" "frontend/src/**/*.tsx" ":!*/tests/*" ":!*.test.*" ":!*test_*.py" ":!backend/application/tests/*" ":!backend/application/tests/**/*" 2>nul || echo.'
        res_src = subprocess.run(cmd_src, shell=True, capture_output=True, text=True, cwd="c:/Repositories/ai-native-reqflow-POC")
        src_files = [f for f in res_src.stdout.strip().split('\n') if f and f.strip() != '.']
        
        # Check tests
        cmd_test = f'git grep -l "{req}" -- "backend/**/test*.py" "backend/**/conftest.py" "frontend/src/**/*.test.ts" "frontend/src/**/*.test.tsx" "e2e/**/*.ts" "backend/application/tests/**/*.py" 2>nul || echo.'
        res_test = subprocess.run(cmd_test, shell=True, capture_output=True, text=True, cwd="c:/Repositories/ai-native-reqflow-POC")
        test_files = [f for f in res_test.stdout.strip().split('\n') if f and f.strip() != '.']
        
        results[req] = {
            'src_files': src_files,
            'test_files': test_files
        }
        
    def repl(match):
        req_id = match.group(2)
        res = results.get(req_id, {'src_files': [], 'test_files': []})
        
        is_implemented = len(res['test_files']) > 0 or len(res['src_files']) > 0
        
        state = "Implemented" if len(res['src_files']) > 0 else "Not Implemented"
        test_status = "Covered" if len(res['test_files']) > 0 else "Missing"
        
        if len(res['src_files']) == 0 and len(res['test_files']) == 0:
            befunde = "Keine Implementierung oder Tests im Code gefunden."
            remarks = "Sollte implementiert werden."
        elif len(res['src_files']) > 0 and len(res['test_files']) == 0:
            befunde = "Implementierung gefunden, aber keine Tests."
            remarks = "Testabdeckung fehlt."
        elif len(res['src_files']) == 0 and len(res['test_files']) > 0:
            befunde = "Nur Tests gefunden, aber keine Implementierung."
            remarks = "Implementierung pr\u00fcfen."
        else:
            befunde = "Anforderung ist durch Tests verifiziert und im Code auffindbar."
            remarks = "Regelm\u00e4\u00dfig auf Regressionen pr\u00fcfen."
            
        insertion = f"**Implementation State:** {state}\n**Review Findings:** {befunde}\n**Test Status:** {test_status}\n**Remarks:** {remarks}\n\n"
        
        block = match.group(0)
        
        # If already inserted previously, replace it
        block = re.sub(r'\*\*Implementation State:\*\*.*?\*\*Remarks:\*\*.*?\n\n', '', block, flags=re.DOTALL)
        block = re.sub(r'\*\*Implementation State:\*\*.*?\*\*Remarks:\*\*.*?\n', '', block, flags=re.DOTALL)
        
        if '**Traceability:**' in block:
            return block.replace('**Traceability:**', insertion + '**Traceability:**')
        elif '**Rationale:**' in block:
            return block.replace('**Rationale:**', insertion + '**Rationale:**')
        else:
            # Append right after the REQ heading and text
            return match.group(1) + "\n\n" + insertion + block[len(match.group(1)):]
            
    # Sub everything
    new_content = re.sub(r'(### (REQ-[A-Z0-9\-]+)[^\n]*\n)(.*?)(?=\n### |\n---|\Z)', repl, content, flags=re.DOTALL)
    
    if new_content != content:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {md_file}")

if __name__ == "__main__":
    check_and_update_dir(sys.argv[1])
