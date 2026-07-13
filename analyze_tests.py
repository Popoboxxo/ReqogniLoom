import os
import ast
import re

REQ_FILE = r"c:\Repositories\ai-native-reqflow-POC\docs\se\L1\Gesamtsystem\L2\ApplicationServiceSystem\L2_ApplicationServiceSystem_Requirements.md"
TESTS_DIR = r"c:\Repositories\ai-native-reqflow-POC\backend\application\tests"
OUTPUT_FILE = r"c:\Repositories\ai-native-reqflow-POC\docs\se\reports\deep_audit\ApplicationServiceSystem_DeepAudit.md"

def main():
    # 1. Parse Requirements
    reqs = {}
    with open(REQ_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    sections = content.split("### REQ-L2-AS-")
    for sec in sections[1:]:
        lines = sec.split('\n')
        req_id = "REQ-L2-AS-" + lines[0].split(':')[0].strip()
        
        ac_match = re.search(r'\*\*Acceptance Criteria:\*\*(.*?)(?=\*\*Interfaces:\*\*|\Z)', sec, re.DOTALL)
        if ac_match:
            ac_text = ac_match.group(1).strip()
        else:
            ac_text = "Keine Akzeptanzkriterien gefunden."
            
        reqs[req_id] = ac_text

    def get_shallow_info(test_source):
        shallow_reasons = []
        refactor_steps = []
        
        patches = re.findall(r'patch\([\'"](.*?)[\'"]\)', test_source)
        patches += re.findall(r'@patch\([\'"](.*?)[\'"]\)', test_source)
        if patches:
            shallow_reasons.append(f"Isoliert die Testumgebung durch `patch` von: {', '.join(patches)}.")
            refactor_steps.append(f"- Entferne die Patches für `{', '.join(patches)}` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.")

        if 'MagicMock' in test_source or 'Mock(' in test_source:
            shallow_reasons.append("Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.")
            refactor_steps.append("- Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.")

        if 'assert_called' in test_source:
            shallow_reasons.append("Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.")
            refactor_steps.append("- Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).")

        if not shallow_reasons:
            currently_does = "Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services."
            refactor_need = "- Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen."
        else:
            currently_does = "Der Test ist **zu oberflächlich (shallow)**. " + " ".join(shallow_reasons)
            refactor_need = "\n".join(refactor_steps) + "\n- Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus."

        return currently_does, refactor_need

    # 2. Parse Tests
    output_lines = ["# Deep Audit: ApplicationServiceSystem Test Coverage\n"]
    output_lines.append("Dieser Report analysiert alle Tests im ApplicationServiceSystem auf Shallow-Testing und listet konkrete Refactoring-Maßnahmen auf.\n")

    for filename in sorted(os.listdir(TESTS_DIR)):
        if not filename.startswith("test_") or not filename.endswith(".py"):
            continue
        filepath = os.path.join(TESTS_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        
        mod_reqs = set(re.findall(r'REQ-L2-AS-\d+', source))
        
        try:
            tree = ast.parse(source)
        except Exception as e:
            output_lines.append(f"## Datei: `{filename}` (Konnte nicht geparst werden: {e})\n")
            continue
            
        output_lines.append(f"## Datei: `{filename}`\n")
        
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                cls_doc = ast.get_docstring(node) or ""
                class_reqs = set(re.findall(r'REQ-L2-AS-\d+', cls_doc))
                
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                        func_doc = ast.get_docstring(item) or ""
                        func_reqs = set(re.findall(r'REQ-L2-AS-\d+', func_doc))
                        
                        all_reqs = func_reqs | class_reqs | mod_reqs
                        req_str = ", ".join(sorted(all_reqs)) if all_reqs else "UNBEKANNT (Keine REQ-ID verlinkt)"
                        
                        test_src = ast.get_source_segment(source, item) or ""
                        currently, refactor = get_shallow_info(test_src)
                        
                        ac = reqs.get(list(sorted(all_reqs))[0] if all_reqs else "", "Keine Akzeptanzkriterien für dieses Requirement gefunden.")
                        
                        output_lines.append(f"### Test: `{item.name}`")
                        output_lines.append(f"- **Verknüpfte REQ-L2 ID:** {req_str}")
                        output_lines.append(f"- **Aktuelles Verhalten:** {currently}")
                        output_lines.append(f"- **Anforderung (Akzeptanzkriterien):**\n  {ac.replace(chr(10), chr(10)+'  ')}")
                        output_lines.append(f"- **Exakter Refactoring-Bedarf:**\n  {refactor.replace(chr(10), chr(10)+'  ')}\n")
                        
            elif isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                func_doc = ast.get_docstring(node) or ""
                func_reqs = set(re.findall(r'REQ-L2-AS-\d+', func_doc))
                
                all_reqs = func_reqs | mod_reqs
                req_str = ", ".join(sorted(all_reqs)) if all_reqs else "UNBEKANNT (Keine REQ-ID verlinkt)"
                
                test_src = ast.get_source_segment(source, node) or ""
                currently, refactor = get_shallow_info(test_src)
                
                ac = reqs.get(list(sorted(all_reqs))[0] if all_reqs else "", "Keine Akzeptanzkriterien für dieses Requirement gefunden.")
                
                output_lines.append(f"### Test: `{node.name}`")
                output_lines.append(f"- **Verknüpfte REQ-L2 ID:** {req_str}")
                output_lines.append(f"- **Aktuelles Verhalten:** {currently}")
                output_lines.append(f"- **Anforderung (Akzeptanzkriterien):**\n  {ac.replace(chr(10), chr(10)+'  ')}")
                output_lines.append(f"- **Exakter Refactoring-Bedarf:**\n  {refactor.replace(chr(10), chr(10)+'  ')}\n")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(output_lines))
    print("Report generated at:", OUTPUT_FILE)

if __name__ == '__main__':
    main()
