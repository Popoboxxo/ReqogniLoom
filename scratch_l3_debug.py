import re

content = """
### REQ-L3-RO-001-01: Asynchrone Entgegennahme

Der AsyncDispatcher SHALL ...
**Domain:** software
**Priority:** mandatory
**Traceability:** REQ-L2-RO-001
"""

req_blocks = re.split(r'### (REQ-L3-[^\n]+)', content)[1:]
for i in range(0, len(req_blocks), 2):
    print("ID:", req_blocks[i])
    print("BODY:", req_blocks[i+1])
