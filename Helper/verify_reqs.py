import os
import re

DOCS_DIR = 'docs/se'
SRC_DIRS = ['backend', 'frontend']

req_pattern = re.compile(r'^### (REQ-L\d[A-Z0-9\-]+)(?:[: —]+)?(.*)$')

def get_all_md_files(directory):
    md_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.md'):
                md_files.append(os.path.join(root, file))
    return md_files

def search_in_codebase(req_id):
    refs = []
    test_refs = []
    for d in SRC_DIRS:
        for root, _, files in os.walk(d):
            for file in files:
                filepath = os.path.join(root, file)
                if not filepath.endswith(('.py', '.ts', '.tsx', '.js', '.jsx')):
                    continue
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if req_id in content:
                            basename = os.path.basename(filepath)
                            if 'test' in filepath.lower() or 'spec' in filepath.lower():
                                test_refs.append(basename)
                            else:
                                refs.append(basename)
                except Exception:
                    pass
    return list(set(refs)), list(set(test_refs))

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    results = []
    
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        match = req_pattern.match(line)
        
        if match:
            req_id = match.group(1).strip()
            refs, test_refs = search_in_codebase(req_id)
            
            impl_state = "Implemented" if refs else "Not Implemented"
            rev_find = f"Code-Referenz in {len(refs)} Datei(en) gefunden (u.a. {refs[0] if refs else ''})." if refs else "Keine direkte Implementierung im Code referenziert."
            if not refs:
                rev_find = "Keine direkte Implementierung im Code referenziert."
                
            test_stat = "Covered" if test_refs else "Missing"
            
            if test_refs:
                rem = f"Test-Referenz in {test_refs[0]} vorhanden."
            elif refs:
                rem = "Fehlende Traceability in den Tests."
            else:
                rem = "REQ-ID taucht im Codebase nicht auf."
                
            results.append({
                'req_id': req_id,
                'impl_state': impl_state,
                'test_stat': test_stat
            })
            
            j = i + 1
            blank_lines = []
            while j < len(lines) and lines[j].strip() == '':
                blank_lines.append(lines[j])
                j += 1
                
            has_existing = False
            if j < len(lines) and lines[j].startswith('**Implementation State:**'):
                has_existing = True
                
            if has_existing:
                while j < len(lines) and (
                    lines[j].startswith('**Implementation State:**') or
                    lines[j].startswith('**Reviewbefunde:**') or
                    lines[j].startswith('**Review Findings:**') or
                    lines[j].startswith('**Test Status:**') or
                    lines[j].startswith('**Remarks:**')
                ):
                    j += 1
                    
                # append the blank lines we skipped
                for bl in blank_lines:
                    new_lines.append(bl)
                    
                new_lines.append(f"**Implementation State:** {impl_state}\n")
                new_lines.append(f"**Reviewbefunde:** {rev_find}\n")
                new_lines.append(f"**Test Status:** {test_stat}\n")
                new_lines.append(f"**Remarks:** {rem}\n")
                
                i = j - 1
            else:
                # no existing fields
                new_lines.append('\n')
                new_lines.append(f"**Implementation State:** {impl_state}\n")
                new_lines.append(f"**Reviewbefunde:** {rev_find}\n")
                new_lines.append(f"**Test Status:** {test_stat}\n")
                new_lines.append(f"**Remarks:** {rem}\n")
                # do not append the extra trailing newline here, it would double-space if there's already a blank line
                # wait, if we don't append a blank line and the next line isn't blank, we should.
                # let's look at the original blank lines we found. If there are none, we add one.
                if len(blank_lines) == 0:
                    new_lines.append('\n')
                # we do NOT advance i, so the next iteration will process i+1 which is whatever was next
                
        i += 1
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
        
    return results

def main():
    md_files = get_all_md_files(DOCS_DIR)
    all_results = []
    
    for f in md_files:
        res = process_file(f)
        all_results.extend(res)
        
    total = len(all_results)
    implemented = sum(1 for r in all_results if r['impl_state'] == 'Implemented')
    tested = sum(1 for r in all_results if r['test_stat'] == 'Covered')
    
    report = f"# System Check Report\n\n"
    report += f"**Datum der Überprüfung:** 2026-06-28\n"
    report += f"**Geprüfte Anforderungen:** {total}\n"
    report += f"**Implementiert:** {implemented} ({(implemented/total*100) if total else 0:.1f}%)\n"
    report += f"**Mit Tests abgedeckt:** {tested} ({(tested/total*100) if total else 0:.1f}%)\n\n"
    
    report += "## Details nach Anforderung\n\n"
    report += "| REQ-ID | Status | Test Status |\n"
    report += "|---|---|---|\n"
    for r in all_results:
        report += f"| {r['req_id']} | {r['impl_state']} | {r['test_stat']} |\n"
        
    artifact_dir = r"C:\Users\duchr\.gemini\antigravity\brain\dc3be559-68fb-46d1-a335-f8573794cd73"
    os.makedirs(artifact_dir, exist_ok=True)
    report_path = os.path.join(artifact_dir, 'system_check_report.md')
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
        
    print(f"Processed {len(md_files)} files. Found {total} requirements.")
    print(f"Report saved to {report_path}")

if __name__ == '__main__':
    main()
