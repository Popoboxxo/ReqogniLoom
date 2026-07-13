import json
with open(r'C:\Repositories\ai-native-reqflow-POC\replacements_chunks_full\replacements_2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print(f"Total chunks: {len(data['ReplacementChunks'])}")
print(f"Target file: {data['TargetFile']}")
