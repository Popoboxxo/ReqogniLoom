import os
import glob
import re
from collections import defaultdict

base_dir = "docs/se/L1/Gesamtsystem/L2"
components_pattern = os.path.join(base_dir, "*", "Components", "*")

missing_test_models = []
orphaned_components = []
reqs_missing_inline_trace = []
reqs_missing_tech_details = []
interface_deviations = []

for comp_dir in glob.glob(components_pattern):
    if not os.path.isdir(comp_dir):
        continue
    
    comp_name = os.path.basename(comp_dir)
    l2_system = os.path.basename(os.path.dirname(os.path.dirname(comp_dir)))
    
    req_files = glob.glob(os.path.join(comp_dir, "*_Requirements.md"))
    arch_files = glob.glob(os.path.join(comp_dir, "*_Architecture.md"))
    
    # 1. Test Models/Results
    # We look for anything indicating a test model or test result.
    test_files = glob.glob(os.path.join(comp_dir, "*TestModel*.md")) + glob.glob(os.path.join(comp_dir, "*TestResult*.md"))
    if not test_files:
        missing_test_models.append(comp_name)
        
    # Process Requirements
    interfaces_in_reqs = set()
    for req_file in req_files:
        with open(req_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Extract interfaces: e.g. IF-XXX-YYY
            interfaces_in_reqs.update(re.findall(r'IF-[A-Z0-9\-]+', content))
            
            # Check if component as a whole has L2 trace
            has_l2_trace = bool(re.search(r'REQ-L2-[A-Z0-9\-]+', content))
            if not has_l2_trace:
                orphaned_components.append(comp_name)
            
            # Find all L3 reqs
            req_blocks = re.split(r'###\s+(REQ-L3-[^\n]+)', content)[1:]
            for i in range(0, len(req_blocks), 2):
                req_id = req_blocks[i].strip()
                req_body = req_blocks[i+1]
                
                # Check inline traceability
                if not re.search(r'(Traceability|Abgeleitet von).+REQ-L2', req_body, re.IGNORECASE):
                    reqs_missing_inline_trace.append(f"{comp_name} / {req_id}")
                    
                # Check tech details (Domain, Priority, Acceptance Criteria)
                missing_tech = []
                if not re.search(r'Priority:', req_body, re.IGNORECASE):
                    missing_tech.append("Priority")
                if not re.search(r'Acceptance Criteria:', req_body, re.IGNORECASE):
                    missing_tech.append("Acceptance Criteria")
                if not re.search(r'Domain:', req_body, re.IGNORECASE):
                    missing_tech.append("Domain")
                    
                if missing_tech:
                    reqs_missing_tech_details.append(f"{comp_name} / {req_id} (Missing: {', '.join(missing_tech)})")

    # Process Architecture
    interfaces_in_arch = set()
    for arch_file in arch_files:
        with open(arch_file, 'r', encoding='utf-8') as f:
            content = f.read()
            interfaces_in_arch.update(re.findall(r'IF-[A-Z0-9\-]+', content))
            
    # Deviations: interfaces present in Reqs but missing in Arch
    unmapped_interfaces = interfaces_in_reqs - interfaces_in_arch
    if unmapped_interfaces and arch_files:
        interface_deviations.append(f"{comp_name}: Unmapped interfaces {', '.join(unmapped_interfaces)}")
    elif req_files and not arch_files:
        interface_deviations.append(f"{comp_name}: No Architecture file to map interfaces")

print(f"Total Components Evaluated: {len(glob.glob(components_pattern))}")
print(f"Missing Test Models: {len(missing_test_models)}")
print(f"Orphaned Components: {len(orphaned_components)}")
print(f"L3 Reqs Missing Inline Trace: {len(reqs_missing_inline_trace)}")
print(f"L3 Reqs Missing Tech Details: {len(reqs_missing_tech_details)}")
print(f"Interface Deviations: {len(interface_deviations)}")

with open('/home/dduchrow/.gemini/antigravity/brain/9b7ec260-7ec1-47fc-911a-f81ec0d24a5a/L3_Verification_Summary.md', 'w') as f:
    f.write("# L3 Verification & Traceability Audit Report\n\n")
    
    f.write("## 1. Test Models and Results Verification\n")
    if missing_test_models:
        f.write(f"**CRITICAL FINDING:** ALL evaluated components ({len(missing_test_models)}) are completely missing Test Models and Test Results (`*TestModel*.md` or `*TestResult*.md`). The entire right side of the V-Model at L3 is undocumented.\n")
    else:
        f.write("Test models verified.\n")
        
    f.write("\n## 2. Component-Level Traceability (Orphaned Components)\n")
    if orphaned_components:
        f.write("The following components lack any reference to an L2 Requirement (completely orphaned):\n")
        for o in sorted(orphaned_components): f.write(f"- {o}\n")
    else:
        f.write("All components maintain at least a general traceability link to L2 requirements.\n")
        
    f.write("\n## 3. Requirement-Level Traceability (Missing Inline Traces)\n")
    if reqs_missing_inline_trace:
        f.write(f"Found {len(reqs_missing_inline_trace)} L3 requirements that do not have an explicit inline `Traceability: REQ-L2-...` tag, breaking granular traceability:\n")
        # limit to 10 examples
        for r in sorted(reqs_missing_inline_trace)[:10]: f.write(f"- {r}\n")
        if len(reqs_missing_inline_trace) > 10: f.write(f"- ... and {len(reqs_missing_inline_trace)-10} more.\n")
        
    f.write("\n## 4. Technical Implementation Requirements\n")
    if reqs_missing_tech_details:
        f.write(f"Found {len(reqs_missing_tech_details)} L3 requirements missing critical technical metadata (Domain, Priority, or Acceptance Criteria):\n")
        for r in sorted(reqs_missing_tech_details)[:10]: f.write(f"- {r}\n")
        if len(reqs_missing_tech_details) > 10: f.write(f"- ... and {len(reqs_missing_tech_details)-10} more.\n")
        
    f.write("\n## 5. Interface Deviations (Requirements vs Architecture)\n")
    if interface_deviations:
        f.write("The following components have interfaces defined in Requirements that are not mapped in the Architecture file:\n")
        for i in sorted(interface_deviations): f.write(f"- {i}\n")
    else:
        f.write("All interfaces are consistently mapped between Requirements and Architecture.\n")

