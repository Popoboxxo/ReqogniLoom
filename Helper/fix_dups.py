import re

with open('docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(
    r'\*\*Implementation State:\*\* To Be Implemented\n\*\*Review Findings:\*\* Ontology Feedback incorporated\.\n\*\*Test Status:\*\* Missing\n\*\*Remarks:\*\* None\.\n\n(→ Siehe `docs/se/L1/Gesamtsystem/L2/(DiagramService|IcdManagement|SeMetrics|ResilienceOrchestrator)System/L2_\2System_Architecture\.md`)',
    r'\1',
    content
)

with open('docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed dups")
