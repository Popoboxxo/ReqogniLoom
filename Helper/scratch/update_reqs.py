import re
import os

files = [
    r"c:\Repositories\ai-native-reqflow-POC\docs\se\L1\Gesamtsystem\L2\ApplicationServiceSystem\Components\COMP-AS-005_TraceLinkService\L3_COMP-AS-005_Requirements.md",
    r"c:\Repositories\ai-native-reqflow-POC\docs\se\L1\Gesamtsystem\L2\ApplicationServiceSystem\Components\COMP-AS-006_BaselineFacade\L3_COMP-AS-006_Requirements.md",
    r"c:\Repositories\ai-native-reqflow-POC\docs\se\L1\Gesamtsystem\L2\ApplicationServiceSystem\Components\COMP-AS-007_WorkflowFacade\L3_COMP-AS-007_WorkflowFacade_Requirements.md",
    r"c:\Repositories\ai-native-reqflow-POC\docs\se\L1\Gesamtsystem\L2\ApplicationServiceSystem\Components\COMP-AS-008_ExportService\L3_COMP-AS-008_ExportService_Requirements.md"
]

data = {
    "REQ-L3-AS005-001": {
        "Implementation State": "Implemented",
        "Review Findings": "Found create_trace_link in trace_link_service.py with extensive type validation and error remapping.",
        "Test Status": "Covered",
        "Remarks": "Multiple unit tests verifying all valid types and error conditions."
    },
    "REQ-L3-AS005-002": {
        "Implementation State": "Implemented",
        "Review Findings": "Found cascade_delete_trace_links in trace_link_service.py.",
        "Test Status": "Covered",
        "Remarks": "Covered by unit tests verifying deletion of upstream and downstream links."
    },
    "REQ-L3-AS005-003": {
        "Implementation State": "Implemented",
        "Review Findings": "Found query_trace_links in trace_link_service.py.",
        "Test Status": "Covered",
        "Remarks": "Covered by tests testing link type filtering and direction."
    },
    "REQ-L3-AS006-001": {
        "Implementation State": "Implemented",
        "Review Findings": "Found preset policy check inside create_baseline.",
        "Test Status": "Covered",
        "Remarks": "Covered by test_scope_not_allowed_raises_validation_error."
    },
    "REQ-L3-AS006-002": {
        "Implementation State": "Implemented",
        "Review Findings": "BaselineCreated domain event emitted after creation.",
        "Test Status": "Covered",
        "Remarks": "Verified by test_audit_called_after_create and test_domain_event_emitted."
    },
    "REQ-L3-AS006-003": {
        "Implementation State": "Implemented",
        "Review Findings": "Found diff_baseline implementation in facade.",
        "Test Status": "Covered",
        "Remarks": "Verified by test_delegates_to_baseline_diff."
    },
    "REQ-L3-WF-001": {
        "Implementation State": "Implemented",
        "Review Findings": "Implementation validates roles via preset policy.",
        "Test Status": "Covered",
        "Remarks": "Covered by multiple tests (e.g. test_passes_when_allowed)."
    },
    "REQ-L3-WF-002": {
        "Implementation State": "Implemented",
        "Review Findings": "Calls workflow engine transition correctly.",
        "Test Status": "Covered",
        "Remarks": "Covered by test_delegates_to_workflow_transition."
    },
    "REQ-L3-WF-003": {
        "Implementation State": "Implemented",
        "Review Findings": "Audit log and domain events are emitted on success.",
        "Test Status": "Covered",
        "Remarks": "Covered by test_audit_called_on_success."
    },
    "REQ-L3-WF-004": {
        "Implementation State": "Implemented",
        "Review Findings": "change_reason validation against preset policy is implemented.",
        "Test Status": "Covered",
        "Remarks": "Covered by test_raises_when_required_and_missing."
    },
    "REQ-L3-WF-005": {
        "Implementation State": "Implemented",
        "Review Findings": "Implements proper error remapping.",
        "Test Status": "Covered",
        "Remarks": "Covered by test_remaps_role_error_to_permission_denied."
    },
    "REQ-L3-WF-006": {
        "Implementation State": "Implemented",
        "Review Findings": "Wraps transitions in transaction.atomic().",
        "Test Status": "Covered",
        "Remarks": "Verified implicitly by event outbox logic and codebase review."
    },
    "REQ-L3-WF-007": {
        "Implementation State": "Not Implemented",
        "Review Findings": "No caching mechanism found in WorkflowFacade.",
        "Test Status": "Missing",
        "Remarks": "Should be implemented for performance optimization."
    },
    "REQ-L3-EXP-001": {
        "Implementation State": "Implemented",
        "Review Findings": "JSON export functionality is fully implemented.",
        "Test Status": "Covered",
        "Remarks": "Verified by test_returns_valid_json."
    },
    "REQ-L3-EXP-002": {
        "Implementation State": "Implemented",
        "Review Findings": "CSV generation and terminology profile header are implemented.",
        "Test Status": "Covered",
        "Remarks": "Verified by test_csv_has_header_and_data_rows."
    },
    "REQ-L3-EXP-003": {
        "Implementation State": "Implemented",
        "Review Findings": "Filter uses artifact_id if provided or workspace_id.",
        "Test Status": "Covered",
        "Remarks": "Covered by implicit fetch logic in unit tests."
    },
    "REQ-L3-EXP-004": {
        "Implementation State": "Implemented",
        "Review Findings": "Uses reportlab via traceability.pdf_report_generator.",
        "Test Status": "Covered",
        "Remarks": "Verified by test_returns_pdf_result."
    },
    "REQ-L3-EXP-005": {
        "Implementation State": "Not Implemented",
        "Review Findings": "No trace links are fetched or included in exports.",
        "Test Status": "Missing",
        "Remarks": "Needs TraceabilityEngine integration."
    },
    "REQ-L3-EXP-006": {
        "Implementation State": "Not Implemented",
        "Review Findings": "Baseline logic is missing in the ExportService.",
        "Test Status": "Missing",
        "Remarks": "Baseline snapshot embedding to be implemented."
    },
    "REQ-L3-EXP-007": {
        "Implementation State": "Not Implemented",
        "Review Findings": "In-memory buffering (StringIO) is used instead of streaming.",
        "Test Status": "Missing",
        "Remarks": "Streaming logic required for large exports."
    },
    "REQ-L3-EXP-008": {
        "Implementation State": "Partially Implemented",
        "Review Findings": "Validates entity types but lacks comprehensive error remapping.",
        "Test Status": "Partially Covered",
        "Remarks": "test_invalid_entity_type_raises exists, but overall error handling needs improvement."
    }
}

for fp in files:
    if not os.path.exists(fp):
        continue
    with open(fp, "r", encoding="utf-8") as f:
        content = f.read()

    # We need to find `### REQ-L3-...: Title`
    # then if it's immediately followed by a blank line and existing **Implementation State**, we replace that block.
    # Otherwise we insert our block after the blank line.

    lines = content.splitlines()
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        m = re.match(r"^###\s+(REQ-L3-[A-Z0-9]+-[0-9]+)", line)
        if m:
            req_id = m.group(1)
            info = data.get(req_id)
            if info:
                # Add the properties
                insert_idx = len(new_lines)
                
                # check if there's existing properties block to skip
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                
                if j < len(lines) and "**Implementation State:**" in lines[j]:
                    # skip until end of properties
                    while j < len(lines) and "**" in lines[j]:
                        j += 1
                    i = j - 1
                else:
                    # just insert after the header
                    pass

                # ensure blank line
                new_lines.append("")
                new_lines.append(f"**Implementation State:** {info['Implementation State']}")
                new_lines.append(f"**Review Findings:** {info['Review Findings']}")
                new_lines.append(f"**Test Status:** {info['Test Status']}")
                new_lines.append(f"**Remarks:** {info['Remarks']}")
                new_lines.append("")
                
                # consume any extra blank lines we might have generated adjacent to
                while i + 1 < len(lines) and lines[i+1].strip() == "":
                    i += 1
                    
        i += 1

    # special cleanup for possible duplicate properties if they weren't caught
    # or just let regex do it. The above logic is simple enough.

    with open(fp, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")
