import os
import glob
import re

base_dir = "docs/se/L1/Gesamtsystem/L2"
components_pattern = os.path.join(base_dir, "*", "Components", "*")

missing_test_models = []
orphaned_traces = []
missing_tech_reqs = []
interface_deviations = []

for comp_dir in glob.glob(components_pattern):
    if not os.path.isdir(comp_dir):
        continue
    
    comp_name = os.path.basename(comp_dir)
    l2_system = os.path.basename(os.path.dirname(os.path.dirname(comp_dir)))
    
    req_files = glob.glob(os.path.join(comp_dir, "*_Requirements.md"))
    arch_files = glob.glob(os.path.join(comp_dir, "*_Architecture.md"))
    test_files = glob.glob(os.path.join(comp_dir, "*Test*.md")) + glob.glob(os.path.join(comp_dir, "*test*.md"))
    
    # 1. Test Models/Results
    if not test_files:
        missing_test_models.append(f"{l2_system} / {comp_name}")
        
    # 2. Requirements & Traceability
    for req_file in req_files:
        with open(req_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Find all L3 reqs
            req_blocks = re.split(r'### (REQ-L3-[^\n]+)', content)[1:]
            for i in range(0, len(req_blocks), 2):
                req_id = req_blocks[i].strip()
                req_body = req_blocks[i+1]
                
                trace_match = re.search(r'\*\*Traceability:\*\*\s*(.+)', req_body, re.IGNORECASE)
                if not trace_match or 'TBD' in trace_match.group(1) or 'None' in trace_match.group(1):
                    orphaned_traces.append(f"**{comp_name}** -> {req_id} (No L2 Trace)")
                else:
                    trace = trace_match.group(1).strip()
                    if not trace.startswith('REQ-L2'):
                        orphaned_traces.append(f"**{comp_name}** -> {req_id} (Invalid L2 trace format: {trace})")
                        
                # Check tech implementation details
                if 'domain:' not in req_body.lower() or 'priority:' not in req_body.lower():
                    missing_tech_reqs.append(f"**{comp_name}** -> {req_id}")

    # 3. Interfaces in Architecture vs Requirements
    for arch_file in arch_files:
        with open(arch_file, 'r', encoding='utf-8') as f:
            arch_content = f.read()
            if 'Schnittstellen' not in arch_content and 'Interfaces' not in arch_content and 'Interface' not in arch_content:
                interface_deviations.append(f"**{comp_name}** (No Interface Mapping in Architecture)")

with open('/home/dduchrow/.gemini/antigravity/brain/9b7ec260-7ec1-47fc-911a-f81ec0d24a5a/L3_Verification_Report.md', 'w') as f:
    f.write("# L3 Verification and Traceability Audit Report\n\n")
    
    f.write("## 1. Missing Test Models / Results\n")
    if missing_test_models:
        for m in sorted(missing_test_models):
            f.write(f"- {m}\n")
    else:
        f.write("None. All components have test models.\n")
        
    f.write("\n## 2. Orphaned Traces (Missing or invalid L2 Traceability)\n")
    if orphaned_traces:
        for o in sorted(orphaned_traces):
            f.write(f"- {o}\n")
    else:
        f.write("None. All L3 requirements trace back to valid L2 requirements.\n")
        
    f.write("\n## 3. Missing Technical Implementation Details (Domain/Priority)\n")
    if missing_tech_reqs:
        for m in sorted(missing_tech_reqs):
            f.write(f"- {m}\n")
    else:
        f.write("None. All L3 requirements define Domain and Priority.\n")
        
    f.write("\n## 4. Interface Deviations (No explicit interface mapping in Architecture)\n")
    if interface_deviations:
        for i in sorted(interface_deviations):
            f.write(f"- {i}\n")
    else:
        f.write("None. All architecture files have interface mappings.\n")

print("Report generated at artifacts/L3_Verification_Report.md")
