import json
with open(r'C:\Repositories\ai-native-reqflow-POC\replacements_chunks_full\replacements_2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
compressed = json.dumps(data, separators=(',', ':'))
print(f"Compressed characters: {len(compressed)}")
