import os
import re
import json
import sys

def modify_md(md_file, results_file):
    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)
        
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    def repl(match):
        req_id = match.group(1)
        res = results.get(req_id, {'src_files': [], 'test_files': []})
        
        is_implemented = len(res['test_files']) > 0 or len(res['src_files']) > 0
        
        state = "Implemented" if is_implemented else "Not Implemented"
        test_status = "Covered" if len(res['test_files']) > 0 else "Missing"
        
        if not is_implemented:
            befunde = "Keine Implementierung im Code gefunden."
            remarks = "Sollte in zukünftigem Sprint berücksichtigt werden."
        else:
            befunde = "Anforderung ist laut Code und/oder Tests umgesetzt."
            remarks = "Regelmäßig auf Regressionen prüfen."
            
        insertion = f"**Implementation State:** {state}\n**Reviewbefunde:** {befunde}\n**Test Status:** {test_status}\n**Remarks:** {remarks}\n"
        
        # We find the Traceability line and insert before it
        trace_match = re.search(r'\*\*Traceability:\*\*', match.group(0))
        if trace_match:
            new_block = match.group(0).replace('**Traceability:**', insertion + '**Traceability:**')
            return new_block
        else:
            # fallback append to the end of the block
            return match.group(0) + '\n' + insertion
            
    # Regex to match a requirement block up to the next ### or ---
    new_content = re.sub(r'(### (REQ-L2-[A-Z]+-\d{3}):.*?)(?=\n### |\n---)', repl, content, flags=re.DOTALL)
    
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Updated {md_file}")

if __name__ == "__main__":
    modify_md(sys.argv[1], sys.argv[2])
