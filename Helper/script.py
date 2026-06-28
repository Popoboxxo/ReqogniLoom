import os
import re
import sys

def search_codebase(req_id, search_path='.'):
    impl_files = []
    test_files = []
    
    for root, dirs, files in os.walk(search_path):
        if '.git' in dirs: dirs.remove('.git')
        if 'node_modules' in dirs: dirs.remove('node_modules')
        if 'venv' in dirs: dirs.remove('venv')
        if '.opencode' in dirs: dirs.remove('.opencode')
        if 'docs' in dirs: dirs.remove('docs')
            
        for file in files:
            if not file.endswith(('.py', '.ts', '.tsx', '.js', '.jsx')):
                continue
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if req_id in content:
                        if 'test' in filepath.lower() or 'tests' in filepath.lower():
                            test_files.append(filepath)
                        else:
                            impl_files.append(filepath)
            except:
                pass
                
    return impl_files, test_files

def process_file(filepath):
    print(f'Processing {filepath}')
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    def replacer(match):
        header = match.group(1)
        req_id_match = re.search(r'### (REQ-[A-Z0-9\-]+):', header)
        if not req_id_match:
            return header
            
        req_id = req_id_match.group(1)
        print(f'  Found {req_id}')
        impl_files, test_files = search_codebase(req_id, '.')
        
        if impl_files:
            impl_state = 'Implemented'
            impl_count = len(impl_files)
            rev_befunde = f'Code-Referenz in {impl_count} Datei(en) gefunden (u.a. {os.path.basename(impl_files[0])}).'
        else:
            impl_state = 'Not Implemented'
            rev_befunde = 'Keine direkte Implementierung im Code referenziert.'
            
        if test_files:
            test_state = 'Covered'
            rem = f'Test-Referenz in {os.path.basename(test_files[0])} vorhanden.'
        else:
            test_state = 'Missing'
            rem = 'Fehlende Traceability in den Tests.'
            
        if not impl_files and not test_files:
            rem = 'REQ-ID taucht im Codebase nicht auf.'
            
        fields = f'\n**Implementation State:** {impl_state}\n**Reviewbefunde:** {rev_befunde}\n**Test Status:** {test_state}\n**Remarks:** {rem}\n'
        return header + fields

    # We only want to replace if **Implementation State:** is NOT immediately following.
    new_content = re.sub(r'(### REQ-[A-Z0-9\-]+:.*?\n)(?!\s*\n*\*\*Implementation State:\*\*)', replacer, content)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f'Saved {filepath}')

for f in sys.argv[1:]:
    process_file(f)
