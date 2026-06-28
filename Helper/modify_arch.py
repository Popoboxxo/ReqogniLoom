import re

with open('docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add UI Level Views to ARCH-L1-001
content = re.sub(
    r'(#### ARCH-L1-001.*?Responsibility:.*?)Stellt Dashboard, Requirements-Editor',
    r'\1Stellt rollenbasierte UI Level Views (z.B. logische/physische Sichten), Dashboard, Requirements-Editor',
    content,
    flags=re.DOTALL
)

# 2. Add Sandboxing to ARCH-L1-003
content = re.sub(
    r'(#### ARCH-L1-003.*?Responsibility:.*?)Nativer MCP-Protokoll-Handler',
    r'\1Nativer MCP-Protokoll-Handler mit striktem Sandboxing (Sicherstellung, dass AI-Agenten keine destruktiven Operationen ohne explizites Approval durchführen). ',
    content,
    flags=re.DOTALL
)

# 3. Add Glossary to ARCH-L1-004 and ARCH-L1-008
content = re.sub(
    r'(#### ARCH-L1-008.*?Responsibility:.*?)Verwaltet Workspace-Presets \(Minimal / Standard / Extended\) und Terminologie-Profile',
    r'\1Verwaltet Workspace-Presets (Minimal / Standard / Extended), ein projektweites Glossary und Terminologie-Profile',
    content,
    flags=re.DOTALL
)

# 4. Add Baseline Recovery to ARCH-L1-006
content = re.sub(
    r'(#### ARCH-L1-006.*?Responsibility:.*?)Stellt Baseline-Vergleichs-Operationen \(Diff\) bereit',
    r'\1Stellt Baseline-Vergleichs-Operationen (Diff) und Baseline Recovery (Wiederherstellung eines Workspaces auf eine frühere Baseline) bereit',
    content,
    flags=re.DOTALL
)

# 5. Add Suspect Linking to ARCH-L1-007
content = re.sub(
    r'(#### ARCH-L1-007.*?Responsibility:.*?)Beantwortet Upstream/Downstream-Queries',
    r'\1Beantwortet Upstream/Downstream-Queries, realisiert Suspect Linking (automatische Markierung nachgelagerter Elemente bei Änderung eines Upstream-Elements)',
    content,
    flags=re.DOTALL
)

# 6. Add Deeper ICD communication to ARCH-L1-014
content = re.sub(
    r'(#### ARCH-L1-014.*?\| \*\*Verantwortlichkeit\*\* \| Verwaltet ICDs.*?mit Feldern für Richtung, Typ, semantische Beschreibung)',
    r'\1, Deeper ICD communication (Message-/Port-Level-Details)',
    content,
    flags=re.DOTALL
)

# Now add the missing fields to A001-A012
# We'll find "→ Siehe docs/..." and add them right before it.
def add_fields_text(match):
    original = match.group(0)
    if "**Implementation State:**" in original:
        return original
    addition = (
        "**Implementation State:** To Be Implemented\n"
        "**Review Findings:** Ontology Feedback incorporated.\n"
        "**Test Status:** Missing\n"
        "**Remarks:** "
    )
    # Give a custom remark if we touched it
    if "ReactFrontendSystem" in original:
        addition += "Includes support for UI Level Views.\n\n"
    elif "McpServerSystem" in original:
        addition += "Includes AI Agent Sandboxing.\n\n"
    elif "BaselineServiceSystem" in original:
        addition += "Includes Baseline Recovery.\n\n"
    elif "TraceabilityEngineSystem" in original:
        addition += "Includes Suspect Linking.\n\n"
    elif "PresetConfigEngineSystem" in original:
        addition += "Includes Glossary management.\n\n"
    else:
        addition += "None.\n\n"
        
    return addition + original

content = re.sub(r'→ Siehe `docs/se/L1/Gesamtsystem/L2/.*?System_Architecture\.md`', add_fields_text, content)

# Now for A013-A016 which are tables.
# We'll find the whole table for these and append rows.
def add_fields_table(match):
    table = match.group(1)
    if "Implementation State" in table:
        return match.group(0)
    
    addition = (
        "| **Implementation State** | To Be Implemented |\n"
        "| **Review Findings** | Ontology Feedback incorporated |\n"
        "| **Test Status** | Missing |\n"
        "| **Remarks** | "
    )
    
    if "IcdManagement" in match.group(0):
        addition += "Includes Deeper ICD communication. |\n"
    else:
        addition += "None. |\n"
        
    # Put the addition at the end of the table
    return match.group(0).replace(table, table + addition)

content = re.sub(r'(#### ARCH-L1-01[3-6].*?\| \*\*Schnittstellen \(ausgehend\)\*\* \|.*?\|\n)', add_fields_table, content, flags=re.DOTALL)


with open('docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("Modified")
