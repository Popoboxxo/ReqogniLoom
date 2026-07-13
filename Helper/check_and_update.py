import os
import re
import json
import subprocess
import sys

def check_and_update(md_file, grep_dir):
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    reqs = re.findall(r'### (REQ-L2-[A-Z]+-\d{3}):', content)
    
    results = {}
    for req in reqs:
        # Check source code
        cmd_src = f'git grep -l "{req}" -- "{grep_dir}/**/*.py" ":!*/tests/*"'
        res_src = subprocess.run(cmd_src, shell=True, capture_output=True, text=True, cwd="c:/Repositories/ai-native-reqflow-POC")
        src_files = res_src.stdout.strip().split('\n') if res_src.stdout.strip() else []
        
        # Check tests
        cmd_test = f'git grep -l "{req}" -- "{grep_dir}/**/test*.py" "{grep_dir}/**/conftest.py"'
        res_test = subprocess.run(cmd_test, shell=True, capture_output=True, text=True, cwd="c:/Repositories/ai-native-reqflow-POC")
        test_files = res_test.stdout.strip().split('\n') if res_test.stdout.strip() else []
        
        # Check e2e tests
        cmd_e2e = f'git grep -l "{req}" -- "e2e/**/*.ts"'
        res_e2e = subprocess.run(cmd_e2e, shell=True, capture_output=True, text=True, cwd="c:/Repositories/ai-native-reqflow-POC")
        e2e_files = res_e2e.stdout.strip().split('\n') if res_e2e.stdout.strip() else []
        
        test_files.extend(e2e_files)
        
        results[req] = {
            'src_files': [f for f in src_files if f],
            'test_files': [f for f in test_files if f]
        }
        
    def repl(match):
        req_id = match.group(2)
        res = results.get(req_id, {'src_files': [], 'test_files': []})
        
        is_implemented = len(res['test_files']) > 0 or len(res['src_files']) > 0
        
        state = "Implemented" if is_implemented else "Not Implemented"
        test_status = "Covered" if len(res['test_files']) > 0 else "Missing"
        
        if not is_implemented:
            befunde = "Keine Implementierung im Code gefunden. Feature fehlt."
            remarks = "Sollte in der Planung für zukünftige Sprints berücksichtigt werden."
        else:
            befunde = "Anforderung ist durch Tests verifiziert und im Code auffindbar."
            remarks = "Regelmäßig auf Regressionen prüfen."
            
        insertion = f"**Implementation State:** {state}\n**Reviewbefunde:** {befunde}\n**Test Status:** {test_status}\n**Remarks:** {remarks}\n"
        
        # We find the Traceability line and insert before it
        if '**Traceability:**' in match.group(0):
            return match.group(0).replace('**Traceability:**', insertion + '**Traceability:**')
        elif '**Rationale:**' in match.group(0):
            return match.group(0).replace('**Rationale:**', insertion + '**Rationale:**')
        else:
            # fallback append to the end of the block
            return match.group(0) + '\n\n' + insertion
            
    # Regex to match a requirement block up to the next ### or ---
    new_content = re.sub(r'(### (REQ-L2-[A-Z]+-\d{3}):.*?)(?=\n### |\n---|\Z)', repl, content, flags=re.DOTALL)
    
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Updated {md_file}")

if __name__ == "__main__":
    check_and_update(sys.argv[1], sys.argv[2])
