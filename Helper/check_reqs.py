import os
import re
import json
import subprocess

def check_reqs(md_file, grep_dir):
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    reqs = re.findall(r'### (REQ-L2-[A-Z]+-\d{3}):.*?', content)
    
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
        
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    import sys
    check_reqs(sys.argv[1], sys.argv[2])
